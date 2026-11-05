"""Build the Module 6 evidence PDF from generated cleaning outputs."""

from pathlib import Path
import json

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak


ROOT = Path(__file__).parent
OUT = ROOT / "output"


def table(data, widths=None):
    converted = [[Paragraph(str(cell), styles["BodyText"]) for cell in row] for row in data]
    t = Table(converted, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17365D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#A6A6A6")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6FA")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleCenter", parent=styles["Title"], alignment=TA_CENTER, textColor=colors.HexColor("#17365D"), spaceAfter=10))
styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=8, leading=10))
styles["BodyText"].leading = 13


def build():
    summary = json.loads((OUT / "validation_summary.json").read_text())
    decisions = __import__("pandas").read_csv(OUT / "cleaning_decision_log.csv")
    missing = __import__("pandas").read_csv(OUT / "missingness.csv")
    checks = __import__("pandas").read_csv(OUT / "record_checks.csv")
    doc = SimpleDocTemplate(str(ROOT / "Module_6_Submission.pdf"), pagesize=letter, rightMargin=.55*inch, leftMargin=.55*inch, topMargin=.5*inch, bottomMargin=.5*inch)
    story = [Paragraph("DSO 576 | Module 6 Project Data Cleaning", styles["TitleCenter"]), Paragraph("Project: Emerging Artist Discovery &nbsp;&nbsp; Student: Kunjesh Gupta", styles["BodyText"]), Spacer(1, 8)]
    story += [Paragraph("Vision and question", styles["Heading2"]), Paragraph("Editorial curation lead at Spotify must decide which emerging artists to add to discovery playlists and which listener segment to surface each one to.", styles["BodyText"]), Paragraph("Cleaning question: Can a cleaned ListenBrainz event sample support descriptive comparisons of artist listen counts and unique listeners by month? The sample is not representative of Spotify users and does not support causal claims.", styles["BodyText"]), Spacer(1, 8)]
    story += [Paragraph("Source and reproducibility", styles["Heading2"]), Paragraph(f"Public source: {summary['source_url']} (user {summary['source_user']}, requested count {summary['source_count']}). Raw file SHA-256: {summary['raw_sha256']}. Run: <font name='Courier'>python3 cleaning_kunjesh/cleaning.py --input cleaning_kunjesh/listenbrainz_sample.json</font>. Expected outputs are in <font name='Courier'>cleaning_kunjesh/output/</font>.", styles["BodyText"]), Spacer(1, 8)]
    story += [Paragraph("14-item checklist", styles["Heading2"])]
    checklist = [
        ["#", "Item", "Status", "Evidence"],
        ["1", "State project vision and question", "Done", "This PDF, Vision and question"],
        ["2", "Define one row", "Done", "cleaning.py flatten_listens; source_index"],
        ["3", "Preserve source", "Done", "Raw JSON and SHA-256 above"],
        ["4", "Inspect columns and types", "Done", "cleaned_listens.csv and conversion flags"],
        ["5", "Standardize text", "Done", "*_raw plus cleaned text columns"],
        ["6", "Investigate duplicates", "Done", f"{summary['exact_duplicates_removed']} exact duplicates removed; repeated IDs retained"],
        ["7", "Handle missing data", "Done", "missingness.csv and metric exclusion flag"],
        ["8", "Check suspicious values", "Done", "invalid/future timestamp and MSID flags"],
        ["9", "Verify merges", "Not applicable", "No merge in event-level pass"],
        ["10", "Reconcile changes", "Done", f"{summary['starting_rows']} starting -> {summary['final_rows']} final rows"],
        ["11", "Check calculations", "Done", "metrics.csv includes listen and unique-listener denominators"],
        ["12", "Verify individual records", "Done", "Five checks on next page"],
        ["13", "Test reproducibility", "Done", "Run command above; generated outputs"],
        ["14", "Document limitations", "Done", "Limitations below"],
    ]
    story += [table(checklist, [0.3*inch, 1.65*inch, 0.9*inch, 4.3*inch]), PageBreak()]
    story += [Paragraph("Cleaning decision log", styles["Heading2"])]
    story += [table([["Rule", "Decision", "Check", "Status"]] + decisions.values.tolist(), [0.75*inch, 2.65*inch, 2.35*inch, .8*inch]), Spacer(1, 10)]
    story += [Paragraph("Missingness before and after cleaning", styles["Heading2"]), table([["Column", "Before", "After"]] + missing.values.tolist(), [2.4*inch, 1.0*inch, 1.0*inch]), PageBreak()]
    story += [Paragraph("Five record checks", styles["Heading2"]), Paragraph("Expected outcomes were defined from the cleaning rules before checking the generated output.", styles["BodyText"]), table([["Source index", "Original", "Expected", "Actual", "Match"]] + checks.values.tolist(), [0.55*inch, 1.25*inch, 2.1*inch, 2.55*inch, .5*inch]), Spacer(1, 10)]
    story += [Paragraph("Limitations and remaining issues", styles["Heading2"]), Paragraph("This 50-listen sample is one public user's history, concentrated in a short historical window. It does not represent mainstream Spotify listeners, does not identify an intervention, and does not prove that an artist is commercially emerging. A production analysis would require a broader population, an explicit emerging-artist definition, a time horizon suitable for growth comparisons, and validated audience-segment features. No table merge was performed, so merge-specific checks remain not applicable.", styles["BodyText"]), Spacer(1, 10), Paragraph("GitHub branch: kunjesh &nbsp;&nbsp; Branch URL: https://github.com/kunjeshgupta/dso576_project/tree/kunjesh &nbsp;&nbsp; Commit ID: fff1c088381a946bd1d2fae77593fc72bf441037 (implementation commit)", styles["Small"])]
    doc.build(story)


if __name__ == "__main__":
    build()
