"""
Compliance Certificate Generator - Additive Compliance Layer

Generates PDF certificates for regulatory attestation.
Does NOT modify core OCX enforcement - only provides audit documentation.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib import colors
import qrcode
from io import BytesIO
from datetime import datetime
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ComplianceCertificateGenerator:
    """
    Generate PDF compliance certificates for governance events.
    
    This is purely for regulatory documentation - it does not affect
    OCX's core enforcement decisions.
    """
    
    def __init__(self, ledger=None):
        """
        Initialize certificate generator.
        
        Args:
            ledger: ImmutableGovernanceLedger instance (optional)
        """
        self.ledger = ledger
        logger.info("Compliance Certificate Generator initialized (additive layer)")
    
    def generate_certificate(self, transaction_id: str, ledger_entry: Dict) -> bytes:
        """
        Generate PDF compliance certificate for a governance event.
        
        Args:
            transaction_id: Transaction ID
            ledger_entry: Ledger entry from ImmutableGovernanceLedger
        
        Returns:
            bytes: PDF file content
        """
        # Create PDF in memory
        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        
        # Title
        pdf.setFont("Helvetica-Bold", 24)
        pdf.drawString(1*inch, height - 1*inch, "OCX Governance Compliance Certificate")
        
        # Subtitle
        pdf.setFont("Helvetica", 12)
        pdf.setFillColor(colors.grey)
        pdf.drawString(1*inch, height - 1.3*inch, "Cryptographic Proof of Policy Enforcement")
        
        # Reset color
        pdf.setFillColor(colors.black)
        
        # Certificate details
        y_position = height - 2*inch
        line_height = 0.25*inch
        
        pdf.setFont("Helvetica-Bold", 10)
        
        # Transaction Information
        pdf.drawString(1*inch, y_position, "Transaction ID:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(2.5*inch, y_position, ledger_entry.get('transaction_id', 'N/A'))
        y_position -= line_height
        
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(1*inch, y_position, "Timestamp:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(2.5*inch, y_position, ledger_entry.get('timestamp', 'N/A'))
        y_position -= line_height
        
        # Agent Information
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(1*inch, y_position, "Agent ID:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(2.5*inch, y_position, ledger_entry.get('agent_id', 'N/A'))
        y_position -= line_height
        
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(1*inch, y_position, "Action:")
        pdf.setFont("Helvetica", 10)
        action_text = ledger_entry.get('action', 'N/A')
        if len(action_text) > 50:
            action_text = action_text[:47] + "..."
        pdf.drawString(2.5*inch, y_position, action_text)
        y_position -= line_height
        
        # Policy Information
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(1*inch, y_position, "Policy Version:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(2.5*inch, y_position, ledger_entry.get('policy_version', 'N/A'))
        y_position -= line_height
        
        # Enforcement Results
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(1*inch, y_position, "Jury Verdict:")
        pdf.setFont("Helvetica", 10)
        verdict = ledger_entry.get('jury_verdict', 'N/A')
        verdict_color = colors.green if verdict == 'PASS' else colors.red
        pdf.setFillColor(verdict_color)
        pdf.drawString(2.5*inch, y_position, verdict)
        pdf.setFillColor(colors.black)
        y_position -= line_height
        
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(1*inch, y_position, "SOP Decision:")
        pdf.setFont("Helvetica", 10)
        pdf.drawString(2.5*inch, y_position, ledger_entry.get('sop_decision', 'N/A'))
        y_position -= line_height
        
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(1*inch, y_position, "PID Verified:")
        pdf.setFont("Helvetica", 10)
        pid_verified = "✓ Yes" if ledger_entry.get('pid_verified') else "✗ No"
        pdf.drawString(2.5*inch, y_position, pid_verified)
        y_position -= line_height
        
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(1*inch, y_position, "Entropy Score:")
        pdf.setFont("Helvetica", 10)
        entropy = ledger_entry.get('entropy_score', 0.0)
        pdf.drawString(2.5*inch, y_position, f"{entropy:.2f}")
        y_position -= line_height * 1.5
        
        # Cryptographic Proof
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(1*inch, y_position, "Cryptographic Proof")
        y_position -= line_height
        
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(1*inch, y_position, "Event Hash:")
        pdf.setFont("Courier", 8)
        event_hash = ledger_entry.get('hash', 'N/A')
        pdf.drawString(1.8*inch, y_position, event_hash)
        y_position -= line_height
        
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(1*inch, y_position, "Previous Hash:")
        pdf.setFont("Courier", 8)
        prev_hash = ledger_entry.get('previous_hash', 'N/A')
        pdf.drawString(1.8*inch, y_position, prev_hash)
        y_position -= line_height * 1.5
        
        # QR Code for verification
        qr_data = f"https://ocx-verify.example.com/verify/{transaction_id}?hash={event_hash}"
        qr = qrcode.QRCode(version=1, box_size=3, border=1)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_buffer = BytesIO()
        qr_img.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)
        
        # Draw QR code
        pdf.drawImage(qr_buffer, 1*inch, y_position - 1.5*inch, width=1.5*inch, height=1.5*inch)
        
        pdf.setFont("Helvetica", 8)
        pdf.drawString(1*inch, y_position - 1.7*inch, "Scan to verify on blockchain")
        
        # Footer
        pdf.setFont("Helvetica-Oblique", 8)
        pdf.setFillColor(colors.grey)
        pdf.drawString(1*inch, 0.5*inch, f"Generated by OCX Governance Ledger on {datetime.utcnow().isoformat()}")
        pdf.drawString(1*inch, 0.3*inch, "This certificate provides cryptographic proof of policy enforcement.")
        
        # Finalize PDF
        pdf.save()
        
        # Get PDF bytes
        buffer.seek(0)
        pdf_bytes = buffer.read()
        
        logger.info(f"Generated compliance certificate for {transaction_id}")
        
        return pdf_bytes
    
    def generate_certificate_by_tx_id(self, transaction_id: str) -> Optional[bytes]:
        """
        Generate certificate by looking up transaction in ledger.
        
        Args:
            transaction_id: Transaction ID
        
        Returns:
            bytes: PDF content or None if not found
        """
        if not self.ledger:
            logger.error("No ledger configured")
            return None
        
        entry = self.ledger.get_event(transaction_id)
        if not entry:
            logger.error(f"Transaction not found: {transaction_id}")
            return None
        
        return self.generate_certificate(transaction_id, entry)


# Example usage
if __name__ == "__main__":
    from immutable_ledger import ImmutableGovernanceLedger
    
    # Create ledger and record event
    ledger = ImmutableGovernanceLedger()
    event = {
        'transaction_id': 'tx-demo-001',
        'agent_id': 'PROCUREMENT_BOT',
        'action': 'execute_payment(vendor="ACME", amount=1500)',
        'policy_version': 'v1.2.3',
        'jury_verdict': 'PASS',
        'entropy_score': 2.3,
        'sop_decision': 'REPLAYED',
        'pid_verified': True
    }
    ledger.record_event(event)
    
    # Generate certificate
    generator = ComplianceCertificateGenerator(ledger)
    pdf_bytes = generator.generate_certificate_by_tx_id('tx-demo-001')
    
    # Save to file
    with open('/tmp/compliance_certificate.pdf', 'wb') as f:
        f.write(pdf_bytes)
    
    print("Certificate generated: /tmp/compliance_certificate.pdf")
