import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch

def draw_logo(c, x, y, size=30):
    """Draws the Stark Minimalism logo."""
    # The SVG path is: M4 17L10 11L14 15L20 7M20 7H15M20 7V12 (on a 24x24 viewBox)
    scale = size / 24.0
    
    # bg-zinc-900 border
    c.setFillColorRGB(0.09, 0.09, 0.1) # #18181b approximate
    c.setStrokeColorRGB(0.15, 0.15, 0.16)
    c.roundRect(x, y, size, size, radius=4, fill=1, stroke=1)
    
    # White lines
    c.setStrokeColorRGB(1, 1, 1)
    c.setLineWidth(2 * scale)
    c.setLineCap(1) # Round cap
    c.setLineJoin(1) # Round join
    
    def tx(vx): return x + vx * scale
    def ty(vy): return y + size - (vy * scale)
    
    # Path 1: M4 17 L10 11 L14 15 L20 7
    p = c.beginPath()
    p.moveTo(tx(4), ty(17))
    p.lineTo(tx(10), ty(11))
    p.lineTo(tx(14), ty(15))
    p.lineTo(tx(20), ty(7))
    
    # M20 7 H15
    p.moveTo(tx(20), ty(7))
    p.lineTo(tx(15), ty(7))
    
    # M20 7 V12
    p.moveTo(tx(20), ty(7))
    p.lineTo(tx(20), ty(12))
    
    c.drawPath(p, stroke=1, fill=0)

def generate_pdf_report(stats_data: dict, date_range: str = "All Time") -> io.BytesIO:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    
    # Fonts
    c.setFont("Helvetica-Bold", 24)
    c.setFillColorRGB(0.05, 0.05, 0.05)
    
    # Header
    draw_logo(c, 40, height - 70, size=35)
    
    c.drawString(90, height - 60, "Performance Overview")
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(90, height - 75, f"Date Range: {date_range}")
    
    c.setStrokeColorRGB(0.9, 0.9, 0.9)
    c.line(40, height - 90, width - 40, height - 90)
    
    # Extract stats
    summary = stats_data.get("summary", {})
    radar = stats_data.get("radar_stats", {})
    funnel = stats_data.get("funnel", {})
    
    # KPI Grid
    c.setFont("Helvetica-Bold", 14)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(40, height - 130, "Key Performance Indicators")
    
    kpis = [
        ("Total Audience", str(summary.get("total_leads", 0))),
        ("Active Campaigns", str(summary.get("active_campaigns", 0))),
        ("Connections (24h)", str(summary.get("connections_today", 0))),
        ("Messages (24h)", str(summary.get("messages_today", 0))),
        ("Inmails (24h)", str(summary.get("inmails_today", 0))),
        ("Account Health", str(summary.get("account_health", "Unknown"))),
        ("Pos. Sentiment", str(summary.get("positive_sentiment", 0))),
        ("Auto-Withdrawals", str(summary.get("auto_withdrawals", 0))),
    ]
    
    start_y = height - 160
    col_width = (width - 80) / 4.0
    
    for i, (label, value) in enumerate(kpis):
        row = i // 4
        col = i % 4
        x = 40 + col * col_width
        y = start_y - row * 50
        
        c.setFont("Helvetica-Bold", 16)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.drawString(x, y, value)
        
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawString(x, y - 14, label.upper())
        
    c.setStrokeColorRGB(0.9, 0.9, 0.9)
    c.line(40, start_y - 80, width - 40, start_y - 80)
    
    # Conversion Funnel & Rates
    c.setFont("Helvetica-Bold", 14)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(40, start_y - 130, "Conversion Funnel & Rates")
    
    rates = [
        ("Acceptance Rate", f"{radar.get('Acceptance Rate', 0):.1f}%"),
        ("Reply Rate", f"{radar.get('Reply Rate', 0):.1f}%"),
        ("Booking Rate", f"{radar.get('Booking Rate', 0):.1f}%"),
        ("Deliverability", f"{radar.get('Deliverability', 100):.1f}%"),
    ]
    
    funnel_steps = [
        ("Extracted", funnel.get("extracted", 0)),
        ("Enrolled", funnel.get("enrolled", 0)),
        ("Connected", funnel.get("connected", 0)),
        ("Replied", funnel.get("replied", 0)),
        ("Booked", funnel.get("booked", 0)),
    ]
    
    # Draw Funnel numbers
    fy = start_y - 170
    c.setFont("Helvetica", 10)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    for label, val in funnel_steps:
        c.drawString(40, fy, f"{label}:")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(120, fy, str(val))
        c.setFont("Helvetica", 10)
        fy -= 20
        
    # Draw Rates
    ry = start_y - 170
    for label, val in rates:
        c.drawString(250, ry, f"{label}:")
        c.setFont("Helvetica-Bold", 10)
        c.drawString(350, ry, str(val))
        c.setFont("Helvetica", 10)
        ry -= 20

    # AI Insight
    ai_insight = stats_data.get("ai_insight")
    if ai_insight:
        c.setStrokeColorRGB(0.9, 0.9, 0.9)
        c.line(40, fy - 20, width - 40, fy - 20)
        
        c.setFont("Helvetica-Bold", 14)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.drawString(40, fy - 60, "Captain's Brief (AI Insight)")
        
        # Simple text wrap
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        
        from reportlab.lib.utils import simpleSplit
        lines = simpleSplit(ai_insight, "Helvetica", 10, width - 80)
        text_y = fy - 80
        for line in lines:
            c.drawString(40, text_y, line)
            text_y -= 14

    c.save()
    buffer.seek(0)
    return buffer
