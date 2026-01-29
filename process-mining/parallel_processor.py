"""
Parallel Document Processor
Handles large batches of 10-15+ documents efficiently
"""

import asyncio
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor
import tempfile
import os

class ParallelDocumentProcessor:
    """Process multiple documents in parallel for speed"""
    
    def __init__(self, document_parser, process_engine, max_workers: int = 5):
        self.document_parser = document_parser
        self.process_engine = process_engine
        self.max_workers = max_workers
    
    async def process_documents_parallel(self, files: List[Any], company_id: str) -> List[Dict[str, Any]]:
        """
        Process multiple documents in parallel
        
        Args:
            files: List of uploaded files
            company_id: Company identifier
        
        Returns:
            List of processed documents with workflows
        """
        # Use ThreadPoolExecutor for I/O-bound operations
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            loop = asyncio.get_event_loop()
            
            # Create tasks for each document
            tasks = []
            for file in files:
                task = loop.run_in_executor(
                    executor,
                    self._process_single_document,
                    file,
                    company_id
                )
                tasks.append(task)
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks)
            
            return results
    
    def _process_single_document(self, file, company_id: str) -> Dict[str, Any]:
        """Process a single document (runs in thread pool)"""
        try:
            # Save temporarily
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
                # Read file content (this is synchronous in the thread)
                content = file.file.read()
                tmp.write(content)
                tmp_path = tmp.name
            
            # Parse document
            mime_type = file.content_type or 'application/pdf'
            parsed = self.document_parser.parse_document(tmp_path, mime_type)
            metadata = self.document_parser.extract_metadata(parsed)
            
            # Extract workflow
            workflow = self.process_engine.extract_complete_workflow(
                document_text=parsed['text'],
                document_type=metadata['document_type'],
                document_metadata=metadata
            )
            
            # Clean up
            os.unlink(tmp_path)
            
            return {
                'document_type': metadata['document_type'],
                'process_table': workflow['process_table'],
                'business_events': workflow['business_events'],
                'metadata': {
                    **metadata,
                    'filename': file.filename
                }
            }
        
        except Exception as e:
            print(f"Error processing {file.filename}: {str(e)}")
            return {
                'document_type': 'Unknown',
                'process_table': [],
                'business_events': [],
                'metadata': {
                    'filename': file.filename,
                    'error': str(e)
                }
            }


class IncrementalMerger:
    """Merge documents incrementally to reduce memory usage"""
    
    def __init__(self, workflow_merger):
        self.workflow_merger = workflow_merger
    
    def merge_incrementally(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge documents incrementally instead of all at once
        
        For 15+ documents, merge in batches of 5 to avoid overwhelming Gemini
        """
        if len(documents) <= 5:
            # Small batch, merge all at once
            return self.workflow_merger.merge_documents(documents)
        
        # Large batch, merge incrementally
        print(f"Large batch detected ({len(documents)} documents). Merging incrementally...")
        
        # Step 1: Group by document type
        grouped = self._group_by_type(documents)
        
        # Step 2: Merge within each group
        merged_groups = []
        for doc_type, docs in grouped.items():
            print(f"Merging {len(docs)} {doc_type} documents...")
            if len(docs) == 1:
                merged_groups.append(docs[0])
            else:
                # Merge in batches of 5
                batches = [docs[i:i+5] for i in range(0, len(docs), 5)]
                batch_results = []
                
                for batch in batches:
                    result = self.workflow_merger.merge_documents(batch)
                    batch_results.append({
                        'document_type': doc_type,
                        'process_table': result['merged_process_table'],
                        'business_events': result['business_events'],
                        'metadata': {
                            'document_type': doc_type,
                            'merged_from': len(batch)
                        }
                    })
                
                # Merge batch results
                if len(batch_results) == 1:
                    merged_groups.append(batch_results[0])
                else:
                    final_merge = self.workflow_merger.merge_documents(batch_results)
                    merged_groups.append({
                        'document_type': doc_type,
                        'process_table': final_merge['merged_process_table'],
                        'business_events': final_merge['business_events'],
                        'metadata': {
                            'document_type': doc_type,
                            'merged_from': len(docs)
                        }
                    })
        
        # Step 3: Final merge across document types
        print(f"Final merge of {len(merged_groups)} document groups...")
        return self.workflow_merger.merge_documents(merged_groups)
    
    def _group_by_type(self, documents: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group documents by type (SOP, Policy, RACI, etc.)"""
        grouped = {}
        for doc in documents:
            doc_type = doc['document_type']
            if doc_type not in grouped:
                grouped[doc_type] = []
            grouped[doc_type].append(doc)
        return grouped


# Example usage
if __name__ == "__main__":
    from document_parser import DocumentParser
    from process_extraction import ProcessExtractionEngine
    from workflow_merger import WorkflowMerger
    
    # Initialize services
    parser = DocumentParser(project_id="ocx-demo", location="us")
    engine = ProcessExtractionEngine(project_id="ocx-demo", location="us-central1")
    merger = WorkflowMerger(project_id="ocx-demo", location="us-central1")
    
    # Create parallel processor
    parallel_processor = ParallelDocumentProcessor(parser, engine, max_workers=5)
    
    # Create incremental merger
    incremental_merger = IncrementalMerger(merger)
    
    # Process 15 documents in parallel
    # documents = await parallel_processor.process_documents_parallel(files, "demo-company")
    
    # Merge incrementally
    # result = incremental_merger.merge_incrementally(documents)
    
    print("Parallel processor ready for 15+ documents")
