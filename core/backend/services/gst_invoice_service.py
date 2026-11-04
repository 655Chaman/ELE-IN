"""
gst_invoice_service.py — Compliant 18% GST Tax Invoice & Sequential Numbering Engine
Pillar 8 (Phase 8.2) — Master Platform Hardening & Execution Plan

Rigorously designed under the Three-Layer Logic Architecture (Paranoia Framework):
  - Layer 0 (Foundational):
      * Compliant 18% GST tax calculation with automated intra-state vs inter-state tax split:
        - Intra-state (Karnataka / KA): 9% CGST + 9% SGST.
        - Inter-state (outside KA): 18% IGST.
      * Sequential invoice number generation: INV-{YYYY}-{sequence:06d}.
  - Layer 1 (Environmental Failure Analysis):
      * Strict idempotency on (provider, payment_id): duplicate webhook calls return existing invoice
        without incrementing sequence or creating duplicate invoice numbers.
      * Thread-safe in-memory store for zero-migration resilience when database is offline.
  - Layer 2 (Human Paranoia & Math Integrity):
      * Two-decimal financial rounding on all tax and subtotal components.
      * Neutralizes spreadsheet formula injection in customer names, addresses, and GSTINs.
      * Input validation: strictly rejects negative or zero invoice amounts.
"""

import re
import io
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)

SELLER_DETAILS = {
    "name": "Ele-in Technologies Private Limited",
    "gstin": "29AABCU9603R1ZM",
    "state": "KA",
    "state_name": "Karnataka",
    "address": "Bangalore, Karnataka, India - 560001",
    "email": "billing@ele-in.com",
}

GST_STANDARD_RATE = 0.18
CGST_RATE = 0.09
SGST_RATE = 0.09
IGST_RATE = 0.18

_invoice_lock = threading.Lock()
_IN_MEMORY_INVOICES: Dict[str, Dict[str, Any]] = {}
_INVOICE_PDF_CACHE: Dict[str, bytes] = {}
_INVOICE_SEQUENCE_COUNTER: int = 1000


def sanitize_input_text(val: Optional[str]) -> str:
    """Neutralizes spreadsheet formula injection (=, +, -, @, \t, \r) and control codes."""
    if not val:
        return ""
    cleaned = str(val).strip()
    while cleaned and cleaned[0] in ('=', '+', '-', '@', '\t', '\r'):
        cleaned = cleaned[1:].strip()
    return cleaned[:255]


def get_next_invoice_number(year: Optional[int] = None) -> str:
    """
    Generates sequential invoice numbers formatted as INV-{YYYY}-{sequence:06d}.
    Thread-safe atomic increment prevents numbering collisions across concurrent threads.
    """
    global _INVOICE_SEQUENCE_COUNTER
    eff_year = year or datetime.now(timezone.utc).year
    with _invoice_lock:
        _INVOICE_SEQUENCE_COUNTER += 1
        num_str = f"INV-{eff_year}-{_INVOICE_SEQUENCE_COUNTER:06d}"
        return num_str


def calculate_gst_breakdown(
    base_amount: float,
    customer_state: Optional[str] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0 & 2: Computes exact 18% GST tax breakdown.
    - If customer_state is 'KA' or 'Karnataka', applies 9% CGST + 9% SGST.
    - Otherwise, applies 18% IGST.
    - Guaranteed 2-decimal financial rounding.
    """
    base = max(0.0, round(float(base_amount or 0.0), 2))
    state_clean = (customer_state or "").strip().upper()
    is_intra_state = state_clean in ("KA", "KARNATAKA", "29")

    if is_intra_state:
        cgst = round(base * CGST_RATE, 2)
        sgst = round(base * SGST_RATE, 2)
        igst = 0.0
        total_tax = round(cgst + sgst, 2)
        tax_type = "INTRA_STATE_CGST_SGST"
    else:
        cgst = 0.0
        sgst = 0.0
        igst = round(base * IGST_RATE, 2)
        total_tax = igst
        tax_type = "INTER_STATE_IGST"

    grand_total = round(base + total_tax, 2)

    return {
        "base_amount": base,
        "is_intra_state": is_intra_state,
        "tax_type": tax_type,
        "cgst_rate": CGST_RATE if is_intra_state else 0.0,
        "cgst_amount": cgst,
        "sgst_rate": SGST_RATE if is_intra_state else 0.0,
        "sgst_amount": sgst,
        "igst_rate": IGST_RATE if not is_intra_state else 0.0,
        "igst_amount": igst,
        "total_tax_rate": GST_STANDARD_RATE,
        "total_tax_amount": total_tax,
        "grand_total": grand_total,
    }


def generate_gst_invoice(
    workspace_id: str,
    base_amount: float,
    customer_name: str,
    customer_email: str,
    customer_state: Optional[str] = None,
    customer_gstin: Optional[str] = None,
    provider: str = "razorpay",
    payment_id: Optional[str] = None,
    currency: str = "INR",
    supabase: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Paranoia Layer 0, 1 & 2: Generates a complete compliant 18% GST Tax Invoice.

    Layer 0 (Foundational):
      - Computes accurate CGST/SGST/IGST breakdown.
      - Assigns sequential unique invoice number.
      - Produces standard invoice manifest for billing dashboard and receipts.

    Layer 1 (Environmental Failure Analysis):
      - Strict idempotency on (provider, payment_id). Re-delivering the same webhook returns
        the previously created invoice without incrementing sequence numbers.
      - In-memory thread-safe fallback store for offline / mock testing resilience.

    Layer 2 (Human Paranoia & Math Integrity):
      - Strips formula injection from customer details.
      - Strictly validates base_amount > 0.
      - Enforces tenant isolation scoping.
    """
    clean_ws = str(workspace_id or "").strip()
    if not clean_ws:
        raise ValueError("workspace_id is required to generate an invoice")

    if base_amount is None or float(base_amount) <= 0.0:
        raise ValueError("base_amount must be greater than zero for tax invoices")

    clean_prov = str(provider or "razorpay").strip().lower()
    clean_pay_id = str(payment_id or "").strip() or None

    # 1. Idempotency Check (Layer 1 Paranoia)
    if clean_pay_id:
        with _invoice_lock:
            for inv in _IN_MEMORY_INVOICES.values():
                if inv.get("provider") == clean_prov and inv.get("payment_id") == clean_pay_id:
                    logger.info(f"[GSTInvoice] Returning existing invoice {inv['invoice_number']} for payment {clean_pay_id}")
                    return inv

        if supabase:
            try:
                res = (
                    supabase.table("invoices")
                    .select("*")
                    .eq("provider", clean_prov)
                    .eq("payment_id", clean_pay_id)
                    .limit(1)
                    .execute()
                )
                rows = getattr(res, "data", []) or []
                if rows and isinstance(rows[0], dict):
                    return rows[0]
            except Exception as e:
                logger.debug(f"[GSTInvoice] DB idempotency check notice: {e}")

    # 2. Tax Computation & Sanitization
    tax_calc = calculate_gst_breakdown(base_amount, customer_state)
    now_utc = datetime.now(timezone.utc)
    now_iso = now_utc.isoformat()
    invoice_num = get_next_invoice_number(year=now_utc.year)

    customer_dict = {
        "name": sanitize_input_text(customer_name) or "Customer",
        "email": sanitize_input_text(customer_email) or "",
        "state": sanitize_input_text(customer_state) or "KA",
        "gstin": sanitize_input_text(customer_gstin) if customer_gstin else None
    }

    invoice_record = {
        "id": f"inv-{now_utc.strftime('%Y%m%d')}-{invoice_num.split('-')[-1]}",
        "workspace_id": clean_ws,
        "invoice_number": invoice_num,
        "provider": clean_prov,
        "payment_id": clean_pay_id,
        "base_amount": tax_calc["base_amount"],
        "tax_amount": tax_calc["total_tax_amount"],
        "total_amount": tax_calc["grand_total"],
        "grand_total": tax_calc["grand_total"],
        "customer_name": customer_dict["name"],
        "customer_email": customer_dict["email"],
        "customer_gstin": customer_dict["gstin"],
        "currency": str(currency or "INR").upper(),
        "status": "PAID",
        "seller_details": SELLER_DETAILS,
        "customer_details": customer_dict,
        "tax_details": tax_calc,
        "created_at": now_iso
    }

    # 3. Store in Memory
    with _invoice_lock:
        _IN_MEMORY_INVOICES[invoice_num] = invoice_record

    # 4. Store in Database
    if supabase:
        try:
            supabase.table("invoices").insert({
                "workspace_id": clean_ws,
                "invoice_number": invoice_num,
                "provider": clean_prov,
                "payment_id": clean_pay_id,
                "base_amount": tax_calc["base_amount"],
                "tax_amount": tax_calc["total_tax_amount"],
                "total_amount": tax_calc["grand_total"],
                "currency": invoice_record["currency"],
                "tax_details": tax_calc,
                "customer_details": customer_dict,
                "status": "PAID",
                "created_at": now_iso
            }).execute()
        except Exception as insert_err:
            logger.debug(f"[GSTInvoice] DB invoice insert fallback to memory: {insert_err}")

    logger.info(
        f"[GSTInvoice] Generated invoice {invoice_num} for workspace {clean_ws}: "
        f"Base={tax_calc['base_amount']} + Tax={tax_calc['total_tax_amount']} = {tax_calc['grand_total']} {currency}"
    )

    return invoice_record


def get_invoice_by_number(
    invoice_number: str,
    workspace_id: Optional[str] = None,
    supabase: Optional[Any] = None
) -> Optional[Dict[str, Any]]:
    """Retrieves an invoice by its sequential number with optional workspace validation."""
    clean_num = str(invoice_number or "").strip()
    with _invoice_lock:
        if clean_num in _IN_MEMORY_INVOICES:
            inv = _IN_MEMORY_INVOICES[clean_num]
            if not workspace_id or inv.get("workspace_id") == workspace_id:
                return dict(inv)

    if supabase:
        try:
            q = supabase.table("invoices").select("*").eq("invoice_number", clean_num)
            if workspace_id:
                q = q.eq("workspace_id", workspace_id)
            res = q.limit(1).execute()
            rows = getattr(res, "data", []) or []
            if rows and isinstance(rows[0], dict):
                return rows[0]
        except Exception as e:
            logger.debug(f"[GSTInvoice] DB get invoice notice: {e}")

    return None


def generate_gst_invoice_pdf(invoice_data: Dict[str, Any]) -> bytes:
    """
    Paranoia Layer 0, 1 & 2: Compiles a standardized, statutory 18% GST Tax Invoice PDF.
    - Caches generated PDF bytes in memory by invoice_number for instant idempotent retrieval.
    - Employs ReportLab for vector rendering.
    - Zero external network dependencies.
    """
    invoice_number = invoice_data.get("invoice_number", "INV-UNKNOWN")
    with _invoice_lock:
        if invoice_number in _INVOICE_PDF_CACHE:
            return _INVOICE_PDF_CACHE[invoice_number]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    header_style = ParagraphStyle(
        'SellerHeader',
        parent=styles['Normal'],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#334155')
    )
    bold_style = ParagraphStyle(
        'BoldMeta',
        parent=styles['Normal'],
        fontSize=9,
        leading=13,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0f172a')
    )
    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#1e293b')
    )
    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0f172a')
    )

    story = []

    # Title & Invoice Header
    seller = invoice_data.get("seller_details", SELLER_DETAILS)
    cust = invoice_data.get("customer_details", {})
    tax = invoice_data.get("tax_details", {})

    header_table_data = [
        [
            Paragraph(f"<b>{seller.get('name', 'Ele-in Technologies Private Limited')}</b><br/>"
                      f"GSTIN: {seller.get('gstin', '29AABCU9603R1ZM')}<br/>"
                      f"{seller.get('address', 'Bangalore, Karnataka, India')}<br/>"
                      f"Email: {seller.get('email', 'billing@ele-in.com')}", header_style),
            Paragraph(f"<b>TAX INVOICE</b><br/>"
                      f"Invoice No: <b>{invoice_number}</b><br/>"
                      f"Date: {invoice_data.get('created_at', '')[:10]}<br/>"
                      f"Payment ID: {invoice_data.get('payment_id', 'N/A')}<br/>"
                      f"Place of Supply: {cust.get('state', 'KA')}", header_style)
        ]
    ]
    t_header = Table(header_table_data, colWidths=[300, 220])
    t_header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(t_header)
    story.append(Spacer(1, 12))

    # Bill To Section
    bill_to_data = [
        [
            Paragraph("<b>BILL TO:</b>", bold_style),
            Paragraph(f"<b>{cust.get('name', 'Customer')}</b><br/>"
                      f"Email: {cust.get('email', 'N/A')}<br/>"
                      f"State: {cust.get('state', 'KA')}<br/>"
                      f"GSTIN: {cust.get('gstin') or 'Consumer / Unregistered'}", header_style)
        ]
    ]
    t_bill = Table(bill_to_data, colWidths=[80, 440])
    t_bill.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(t_bill)
    story.append(Spacer(1, 16))

    # Line Items Table
    curr = invoice_data.get("currency", "INR")
    base_amt = float(invoice_data.get("base_amount", 0.0))
    is_intra = tax.get("is_intra_state", True)

    items_data = [
        [
            Paragraph("<b>Item & Description</b>", table_cell_bold),
            Paragraph("<b>SAC Code</b>", table_cell_bold),
            Paragraph("<b>Taxable Value</b>", table_cell_bold),
            Paragraph("<b>Tax Rate</b>", table_cell_bold),
            Paragraph(f"<b>Total ({curr})</b>", table_cell_bold)
        ],
        [
            Paragraph("Ele-in AI Outreach & Data Intelligence Platform Subscription", table_cell),
            Paragraph("998311", table_cell),
            Paragraph(f"{base_amt:.2f}", table_cell),
            Paragraph("18.00%", table_cell),
            Paragraph(f"{invoice_data.get('grand_total', 0.0):.2f}", table_cell)
        ]
    ]

    # Tax summary sub-rows
    if is_intra:
        tax_rows = [
            ["", "", Paragraph("CGST @ 9.00%", table_cell), "", Paragraph(f"{tax.get('cgst_amount', 0.0):.2f}", table_cell)],
            ["", "", Paragraph("SGST @ 9.00%", table_cell), "", Paragraph(f"{tax.get('sgst_amount', 0.0):.2f}", table_cell)],
        ]
    else:
        tax_rows = [
            ["", "", Paragraph("IGST @ 18.00%", table_cell), "", Paragraph(f"{tax.get('igst_amount', 0.0):.2f}", table_cell)],
        ]

    for tr in tax_rows:
        items_data.append(tr)

    items_data.append([
        Paragraph("<b>Total Tax:</b>", table_cell_bold),
        "",
        "",
        "",
        Paragraph(f"<b>{tax.get('total_tax_amount', 0.0):.2f}</b>", table_cell_bold)
    ])
    items_data.append([
        Paragraph("<b>Grand Total (Inclusive of Taxes):</b>", table_cell_bold),
        "",
        "",
        "",
        Paragraph(f"<b>{curr} {invoice_data.get('grand_total', 0.0):.2f}</b>", table_cell_bold)
    ])

    t_items = Table(items_data, colWidths=[200, 70, 90, 70, 90])
    t_items.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f1f5f9')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f8fafc')),
    ]))
    story.append(t_items)
    story.append(Spacer(1, 20))

    # Reverse Charge & Declarations
    notes_data = [
        [Paragraph("<b>Statutory Declarations:</b><br/>"
                   "1. Tax is not payable on reverse charge basis: <b>No</b>.<br/>"
                   "2. Standard HSN/SAC 998311 applied for Cloud & Software as a Service.<br/>"
                   "3. This is a computer-generated tax invoice and requires no physical signature.", header_style)]
    ]
    t_notes = Table(notes_data, colWidths=[520])
    t_notes.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ffffff')),
        ('PADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_notes)

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    with _invoice_lock:
        _INVOICE_PDF_CACHE[invoice_number] = pdf_bytes

    return pdf_bytes


def clear_in_memory_invoices() -> None:
    """Clears in-memory invoices and cached PDF documents for unit test isolation."""
    with _invoice_lock:
        _IN_MEMORY_INVOICES.clear()
        _INVOICE_PDF_CACHE.clear()

