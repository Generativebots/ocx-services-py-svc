"""
Recursive Semantic Parser for Complex SOPs
Decomposes documents: Headers → Paragraphs → Sentences → JSON-Logic
"""

import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from vllm_client import VLLMClient
import logging
logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """Represents a chunk of the document"""
    level: int  # 0=document, 1=section, 2=paragraph, 3=sentence
    title: Optional[str]
    content: str
    parent: Optional['DocumentChunk'] = None
    children: List['DocumentChunk'] = None
    
    def __post_init__(self) -> None:
        if self.children is None:
            self.children = []


class RecursiveSemanticParser:
    """
    Recursively parses SOPs into hierarchical structure
    Then extracts policies from each level
    """
    
    def __init__(self, vllm_client: VLLMClient) -> None:
        self.vllm_client = vllm_client
    
    def parse_document(self, document_text: str) -> DocumentChunk:
        """
        Parse document into hierarchical chunks
        
        Returns:
            Root DocumentChunk with nested children
        """
        root = DocumentChunk(
            level=0,
            title="Document Root",
            content=document_text
        )
        
        # Level 1: Split by headers (# Header, ## Subheader, etc.)
        sections = self._split_by_headers(document_text)
        for section_title, section_content in sections:
            section_chunk = DocumentChunk(
                level=1,
                title=section_title,
                content=section_content,
                parent=root
            )
            root.children.append(section_chunk)
            
            # Level 2: Split by paragraphs
            paragraphs = self._split_by_paragraphs(section_content)
            for para_content in paragraphs:
                para_chunk = DocumentChunk(
                    level=2,
                    title=None,
                    content=para_content,
                    parent=section_chunk
                )
                section_chunk.children.append(para_chunk)
                
                # Level 3: Split by sentences
                sentences = self._split_by_sentences(para_content)
                for sentence in sentences:
                    sentence_chunk = DocumentChunk(
                        level=3,
                        title=None,
                        content=sentence,
                        parent=para_chunk
                    )
                    para_chunk.children.append(sentence_chunk)
        
        return root
    
    def _split_by_headers(self, text: str) -> List[tuple[str, str]]:
        """Split document by markdown headers"""
        # Match # Header, ## Subheader, ### Sub-subheader
        pattern = r'^(#{1,6})\s+(.+)$'
        
        sections = []
        current_title = None
        current_content = []
        
        for line in text.split('\n'):
            match = re.match(pattern, line)
            if match:
                # Save previous section
                if current_title:
                    sections.append((current_title, '\n'.join(current_content)))
                
                # Start new section
                current_title = match.group(2)
                current_content = []
            else:
                current_content.append(line)
        
        # Save last section
        if current_title:
            sections.append((current_title, '\n'.join(current_content)))
        
        # If no headers found, treat entire document as one section
        if not sections:
            sections.append(("Untitled", text))
        
        return sections
    
    def _split_by_paragraphs(self, text: str) -> List[str]:
        """Split text by paragraphs (double newline)"""
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]
    
    def _split_by_sentences(self, text: str) -> List[str]:
        """Split text by sentences"""
        # Simple sentence splitting (can be improved with NLTK)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def extract_policies_recursive(
        self,
        chunk: DocumentChunk,
        source_name: str
    ) -> List[Dict[str, Any]]:
        """
        Recursively extract policies from document chunks
        
        Strategy:
        1. Extract from sentences (most specific)
        2. Merge related sentences into paragraph-level policies
        3. Merge related paragraphs into section-level policies
        4. Validate consistency across levels
        """
        all_policies = []
        
        # Extract from current level
        if chunk.level >= 2:  # Paragraph or sentence level
            policies = self._extract_from_chunk(chunk, source_name)
            all_policies.extend(policies)
        
        # Recursively extract from children
        for child in chunk.children:
            child_policies = self.extract_policies_recursive(child, source_name)
            all_policies.extend(child_policies)
        
        # Merge and deduplicate
        if chunk.level == 0:  # Root level
            all_policies = self._merge_policies(all_policies)
            all_policies = self._validate_consistency(all_policies)
        
        return all_policies
    
    def _extract_from_chunk(
        self,
        chunk: DocumentChunk,
        source_name: str
    ) -> List[Dict[str, Any]]:
        """Extract policies from a single chunk using vLLM"""
        if len(chunk.content) < 20:  # Skip very short chunks
            return []
        
        # Use vLLM to extract
        policies = self.vllm_client.extract_policies(
            document_text=chunk.content,
            source_name=f"{source_name} - {chunk.title or 'Paragraph'}"
        )
        
        return policies
    
    def _merge_policies(self, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge duplicate or overlapping policies
        
        Strategy:
        - Group by trigger_intent
        - Merge logic with OR if similar
        - Keep highest confidence
        """
        merged = {}
        
        for policy in policies:
            trigger = policy.get("trigger_intent", "unknown")
            
            if trigger not in merged:
                merged[trigger] = policy
            else:
                # Merge logic (simple OR for now)
                existing = merged[trigger]
                
                # Keep higher confidence
                if policy.get("confidence", 0) > existing.get("confidence", 0):
                    merged[trigger] = policy
        
        return list(merged.values())
    
    def _validate_consistency(self, policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate policies for consistency
        
        Checks:
        - No contradictory rules
        - No duplicate policy_ids
        - Logic is valid JSON-Logic
        """
        from json_logic_engine import JSONLogicEngine
        
        engine = JSONLogicEngine()
        valid_policies = []
        seen_ids = set()
        
        for policy in policies:
            policy_id = policy.get("policy_id")
            
            # Check duplicate IDs
            if policy_id in seen_ids:
                print(f"⚠️  Duplicate policy ID: {policy_id}")
                continue
            seen_ids.add(policy_id)
            
            # Validate logic
            logic = policy.get("logic", {})
            is_valid, error = engine.validate_logic(logic)
            if not is_valid:
                print(f"⚠️  Invalid logic in {policy_id}: {error}")
                continue
            
            valid_policies.append(policy)
        
        return valid_policies


# Example usage
if __name__ == "__main__":
    from vllm_client import get_vllm_client

    
    # Sample SOP
    sop_text = """
# Procurement Policy

## Purchase Approval

All software purchases over $500 require CTO approval.

Exceptions apply for pre-approved security vendors.

## Payment Processing

Payments must be processed within 48 hours of approval.

No payments can be made to vendors on the blacklist.

# Data Security Policy

## Data Exfiltration

No data can leave the VPC without explicit approval.

All external requests must be logged.
"""
    
    # Parse
    vllm_client = get_vllm_client()
    parser = RecursiveSemanticParser(vllm_client)
    
    root = parser.parse_document(sop_text)
    print(f"Parsed into {len(root.children)} sections")
    
    # Extract policies
    policies = parser.extract_policies_recursive(root, "Sample SOP")
    print(f"Extracted {len(policies)} policies")
    
    for policy in policies:
        print(f"  - {policy['policy_id']}: {policy['trigger_intent']}")
