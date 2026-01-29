"""
Process Mining Engine - Document Parser
Uses Google Document AI for OCR and document parsing
"""

import os
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
from typing import Dict, List, Any
import json

class DocumentParser:
    """Parse business documents using Google Document AI"""
    
    def __init__(self, project_id: str, location: str = "us"):
        self.project_id = project_id
        self.location = location
        self.client = documentai.DocumentProcessorServiceClient()
        
        # Document AI processor for general documents
        self.processor_name = self.client.processor_path(
            project_id, location, os.getenv('DOCUMENT_AI_PROCESSOR_ID')
        )
    
    def parse_document(self, file_path: str, mime_type: str) -> Dict[str, Any]:
        """
        Parse a business document and extract structured data
        
        Args:
            file_path: Path to document file
            mime_type: MIME type (application/pdf, text/plain, etc.)
        
        Returns:
            Parsed document with text, entities, and structure
        """
        # Read file
        with open(file_path, 'rb') as f:
            file_content = f.read()
        
        # Create Document AI request
        raw_document = documentai.RawDocument(
            content=file_content,
            mime_type=mime_type
        )
        
        request = documentai.ProcessRequest(
            name=self.processor_name,
            raw_document=raw_document
        )
        
        # Process document
        result = self.client.process_document(request=request)
        document = result.document
        
        # Extract structured data
        parsed = {
            'text': document.text,
            'pages': len(document.pages),
            'entities': self._extract_entities(document),
            'paragraphs': self._extract_paragraphs(document),
            'tables': self._extract_tables(document),
            'confidence': document.confidence if hasattr(document, 'confidence') else 0.0
        }
        
        return parsed
    
    def _extract_entities(self, document) -> List[Dict[str, Any]]:
        """Extract entities from document"""
        entities = []
        
        for entity in document.entities:
            entities.append({
                'type': entity.type_,
                'mention_text': entity.mention_text,
                'confidence': entity.confidence,
                'normalized_value': entity.normalized_value.text if hasattr(entity, 'normalized_value') else None
            })
        
        return entities
    
    def _extract_paragraphs(self, document) -> List[str]:
        """Extract paragraphs from document"""
        paragraphs = []
        
        for page in document.pages:
            for paragraph in page.paragraphs:
                text = self._get_text(document.text, paragraph.layout.text_anchor)
                paragraphs.append(text)
        
        return paragraphs
    
    def _extract_tables(self, document) -> List[Dict[str, Any]]:
        """Extract tables from document"""
        tables = []
        
        for page in document.pages:
            for table in page.tables:
                table_data = {
                    'rows': len(table.body_rows),
                    'columns': len(table.header_rows[0].cells) if table.header_rows else 0,
                    'headers': [],
                    'data': []
                }
                
                # Extract headers
                if table.header_rows:
                    for cell in table.header_rows[0].cells:
                        text = self._get_text(document.text, cell.layout.text_anchor)
                        table_data['headers'].append(text)
                
                # Extract data rows
                for row in table.body_rows:
                    row_data = []
                    for cell in row.cells:
                        text = self._get_text(document.text, cell.layout.text_anchor)
                        row_data.append(text)
                    table_data['data'].append(row_data)
                
                tables.append(table_data)
        
        return tables
    
    def _get_text(self, full_text: str, text_anchor) -> str:
        """Extract text from text anchor"""
        if not text_anchor or not text_anchor.text_segments:
            return ""
        
        text = ""
        for segment in text_anchor.text_segments:
            start = int(segment.start_index) if hasattr(segment, 'start_index') else 0
            end = int(segment.end_index) if hasattr(segment, 'end_index') else len(full_text)
            text += full_text[start:end]
        
        return text.strip()
    
    def identify_document_type(self, parsed_doc: Dict[str, Any]) -> str:
        """
        Identify document type based on content
        
        Returns:
            Document type: SOP, Policy, BRD, FRD, RACI, Workflow, etc.
        """
        text = parsed_doc['text'].lower()
        
        # Check for SOP indicators
        if 'standard operating procedure' in text or 'sop' in text:
            return 'SOP'
        
        # Check for policy indicators
        if 'policy' in text and ('compliance' in text or 'regulation' in text):
            return 'Policy'
        
        # Check for BRD indicators
        if 'business requirements' in text or 'brd' in text:
            return 'BRD'
        
        # Check for FRD indicators
        if 'functional requirements' in text or 'frd' in text:
            return 'FRD'
        
        # Check for RACI matrix
        if 'responsible' in text and 'accountable' in text and 'consulted' in text:
            return 'RACI'
        
        # Check for workflow
        if 'workflow' in text or 'process flow' in text:
            return 'Workflow'
        
        # Default
        return 'Unknown'
    
    def extract_metadata(self, parsed_doc: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata from document"""
        metadata = {
            'document_type': self.identify_document_type(parsed_doc),
            'page_count': parsed_doc['pages'],
            'confidence': parsed_doc['confidence'],
            'has_tables': len(parsed_doc['tables']) > 0,
            'entity_count': len(parsed_doc['entities'])
        }
        
        # Extract version from text
        text = parsed_doc['text']
        if 'version' in text.lower():
            # Simple regex to find version numbers
            import re
            version_match = re.search(r'version\s*:?\s*(\d+\.\d+\.?\d*)', text.lower())
            if version_match:
                metadata['version'] = version_match.group(1)
        
        # Extract owner/department
        for entity in parsed_doc['entities']:
            if entity['type'] in ['ORGANIZATION', 'PERSON']:
                metadata['owner'] = entity['mention_text']
                break
        
        return metadata


class DocumentStorage:
    """Store documents in Google Cloud Storage"""
    
    def __init__(self, bucket_name: str):
        self.bucket_name = bucket_name
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)
    
    def upload_document(self, file_path: str, destination_path: str) -> str:
        """Upload document to Cloud Storage"""
        blob = self.bucket.blob(destination_path)
        blob.upload_from_filename(file_path)
        
        return f"gs://{self.bucket_name}/{destination_path}"
    
    def download_document(self, source_path: str, destination_path: str):
        """Download document from Cloud Storage"""
        blob = self.bucket.blob(source_path)
        blob.download_to_filename(destination_path)
    
    def list_documents(self, prefix: str = "") -> List[str]:
        """List documents in Cloud Storage"""
        blobs = self.bucket.list_blobs(prefix=prefix)
        return [blob.name for blob in blobs]


# Example usage
if __name__ == "__main__":
    # Initialize parser
    parser = DocumentParser(
        project_id=os.getenv('GOOGLE_CLOUD_PROJECT'),
        location='us'
    )
    
    # Parse a sample document
    parsed = parser.parse_document(
        file_path='demo-documents/purchase_order_sop.txt',
        mime_type='text/plain'
    )
    
    print(f"Document Type: {parser.identify_document_type(parsed)}")
    print(f"Pages: {parsed['pages']}")
    print(f"Entities: {len(parsed['entities'])}")
    print(f"Paragraphs: {len(parsed['paragraphs'])}")
    print(f"Tables: {len(parsed['tables'])}")
    
    # Extract metadata
    metadata = parser.extract_metadata(parsed)
    print(f"Metadata: {json.dumps(metadata, indent=2)}")
