"""Build an editable, evidence-led draft for a user's SEBI reporting workflow.

This generates a Word document using only the Python standard library. It does
not make legal findings: the audit output is labeled as automated screening and
the reporter is asked to verify every fact before filing.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
from typing import Any
import zipfile


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SCORES_URL = "https://scores.sebi.gov.in/"
SCORES_FAQ_URL = "https://scores.sebi.gov.in/faqs"
MI_PORTAL_URL = "https://miportal.sebi.gov.in/"


def _text(value: Any, limit: int = 6000) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        value = "; ".join(str(item) for item in value)
    return str(value).strip()[:limit]


def _unique_text(values: list[Any], limit: int = 40) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _text(value, 1500)
        key = item.casefold()
        if item and key not in seen:
            seen.add(key)
            result.append(item)
        if len(result) >= limit:
            break
    return result


def _items(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value] if value else []


def _paragraph(text: str, style: str | None = None, bold: bool = False) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{escape(style)}"/></w:pPr>' if style else ""
    runs = []
    for index, line in enumerate(str(text).split("\n")):
        if index:
            runs.append("<w:r><w:br/></w:r>")
        rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
        runs.append(f'<w:r>{rpr}<w:t xml:space="preserve">{escape(line)}</w:t></w:r>')
    return f"<w:p>{ppr}{''.join(runs)}</w:p>"


def _docx(paragraphs: list[str]) -> bytes:
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(paragraphs) +
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080" '
        'w:header="540" w:footer="540" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )
    styles_xml = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos"/><w:sz w:val="21"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:rPr><w:b/><w:color w:val="17365D"/><w:sz w:val="32"/></w:rPr><w:pPr><w:keepNext/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:color w:val="17365D"/><w:sz w:val="26"/></w:rPr><w:pPr><w:keepNext/><w:spacing w:before="240" w:after="100"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:rPr><w:b/><w:color w:val="365F91"/><w:sz w:val="23"/></w:rPr><w:pPr><w:keepNext/><w:spacing w:before="180" w:after="60"/></w:pPr></w:style>
</w:styles>'''
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>'''
    root_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
    document_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>'''
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", styles_xml)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
    return output.getvalue()


def build_scores_complaint_draft(payload: dict[str, Any]) -> bytes:
    audit = payload.get("audit") if isinstance(payload.get("audit"), dict) else {}
    overall = _text(audit.get("overall_status")).upper()
    if overall != "HIGH RISK":
        raise ValueError("A complaint draft can only be generated for a HIGH RISK audit result.")

    analysis = audit.get("document_analysis") if isinstance(audit.get("document_analysis"), dict) else {}
    p1 = audit.get("process_1_sebi") if isinstance(audit.get("process_1_sebi"), dict) else {}
    p2 = audit.get("process_2_risk_audit") if isinstance(audit.get("process_2_risk_audit"), dict) else {}
    generated = datetime.now().astimezone().strftime("%d %B %Y, %I:%M %p %Z")
    summary = _text(analysis.get("document_summary") or audit.get("ai_summary"), 5000) or "No AI summary was returned."
    message = _text(payload.get("input_text"), 10000)
    username = _text(payload.get("claimed_username"), 500)
    filename = _text(payload.get("uploaded_filename"), 300)
    risk_score = _text(p2.get("risk_score"), 40) or "Not returned"
    risk_badge = _text(p2.get("badge"), 200) or "Not returned"
    official_entity = _text(p1.get("official_entity"), 500) or "Not identified"
    primary_sebi = _text(p1.get("sebi_number"), 100) or "Not extracted"

    rows: list[str] = [
        _paragraph("DRAFT — INVESTOR GRIEVANCE / SUSPECTED IMPERSONATION REPORT", "Title"),
        _paragraph(f"Prepared from a local automated screening result on {generated}."),
        _paragraph("IMPORTANT: This is an editable factual draft, not legal advice, a legal notice, or a finding that any person committed fraud. A HIGH RISK score is an automated screening signal only. Verify every statement against original evidence, correct errors, and remove anything you cannot personally support before submitting. Do not publish allegations based only on this automated result."),
        _paragraph("1. Reporter and case details", "Heading1"),
        _paragraph("Reporter’s full legal name: [Complete as required]\nPostal address: [Complete]\nEmail and mobile: [Complete]\nDate of incident / first contact: [Complete]\nPlace / online channel where contact occurred: [Complete]\nSCORES complaint / prior entity grievance reference (if any): [Complete or write ‘Not filed’]"),
        _paragraph("SCORES registration note: SEBI’s current FAQ lists name, address, email address, PAN, mobile number, and date of birth as mandatory KYC information for portal registration. Enter sensitive KYC details directly on the official SCORES portal; this downloaded draft does not collect or contain PAN or date of birth."),
        _paragraph("2. Person, entity, registration and contact details shown in the evidence", "Heading1"),
        _paragraph(f"Extracted name(s): {_text(analysis.get('registered_company_names')) or username or 'None extracted'}\nEntity returned from local registration lookup: {official_entity}\nExtracted SEBI registration number(s): {_text(analysis.get('sebi_registration_numbers')) or primary_sebi}\nAccount / handle separately entered: {username or 'None entered'}\nExtracted URL(s): {_text(analysis.get('urls')) or 'None extracted'}\nUploaded evidence filename: {filename or 'No upload (typed text only)'}"),
        _paragraph("3. Facts and nature of concern", "Heading1"),
        _paragraph("I request review of the communication or material identified below. The following is a machine-generated summary and must be checked against the original: " + summary),
    ]

    if message:
        rows.extend([_paragraph("Message text supplied to the checker", "Heading2"), _paragraph(message)])

    registrations = p1.get("registration_checks") if isinstance(p1.get("registration_checks"), list) else []
    rows.append(_paragraph("4. Registration checks returned by the checker", "Heading1"))
    if registrations:
        for check in registrations[:30]:
            if not isinstance(check, dict):
                continue
            rows.append(_paragraph(
                f"SEBI ID: {_text(check.get('sebi_number')) or 'Not stated'} | Result: {_text(check.get('status')) or 'Not returned'}\n"
                f"Entity returned: {_text(check.get('official_entity')) or 'Not identified'}\n"
                f"Explanation: {_text(check.get('explanation')) or 'No explanation returned.'}"
            ))
    else:
        rows.append(_paragraph(f"No individual registration check was returned. Process 1 result: {_text(p1.get('badge')) or 'Not returned'}. {_text(p1.get('reason_en'))}"))

    name_checks = p1.get("name_checks") if isinstance(p1.get("name_checks"), list) else []
    username_checks = p1.get("username_checks") if isinstance(p1.get("username_checks"), list) else []
    if name_checks or username_checks:
        rows.append(_paragraph("Name and username comparisons", "Heading2"))
        for check in (name_checks + username_checks)[:40]:
            if isinstance(check, dict):
                rows.append(_paragraph(
                    f"Name / handle: {_text(check.get('name') or check.get('claimed_username')) or 'Not stated'} | "
                    f"SEBI ID: {_text(check.get('sebi_number')) or 'Not linked'} | "
                    f"Result: {_text(check.get('status')) or 'Not returned'}\n"
                    f"Explanation: {_text(check.get('explanation')) or 'No explanation returned.'}"
                ))

    urls = p1.get("urls_checked") if isinstance(p1.get("urls_checked"), list) else []
    rows.append(_paragraph("5. URLs and association checks", "Heading1"))
    if urls:
        for check in urls[:30]:
            if not isinstance(check, dict):
                continue
            rows.append(_paragraph(f"URL: {_text(check.get('url'))}\nResult: {_text(check.get('status')) or 'Not returned'}\nExplanation: {_text(check.get('explanation')) or 'No explanation returned.'}"))
            for pair in (check.get("combinations") or [])[:30]:
                if isinstance(pair, dict):
                    rows.append(_paragraph(
                        f"Association: {_text(pair.get('url')) or _text(check.get('url'))} × "
                        f"{_text(pair.get('sebi_number')) or 'No SEBI ID'} × {_text(pair.get('name')) or 'No name'}\n"
                        f"Result: {_text(pair.get('status')) or 'Not returned'} — {_text(pair.get('explanation')) or 'No explanation returned.'}"
                    ))
        checked_urls = {_text(check.get("url")).casefold() for check in urls if isinstance(check, dict)}
        for raw_url in _unique_text(_items(analysis.get("urls")), 40):
            if raw_url.casefold() not in checked_urls:
                rows.append(_paragraph(f"URL extracted but no separate association result was returned: {raw_url}"))
    else:
        extracted_urls = _unique_text(_items(analysis.get("urls")), 40)
        rows.append(_paragraph("Extracted URL(s):\n" + ("\n".join(extracted_urls) if extracted_urls else "No URL was extracted from the submitted evidence.")))

    flags = _unique_text(
        _items(analysis.get("red_flags")) + _items(p1.get("red_flags")) + _items(p2.get("detected_flags"))
        + _items(analysis.get("visual_anomalies"))
    )
    rows.extend([
        _paragraph("6. Automated screening result and stated indicators", "Heading1"),
        _paragraph(f"Overall checker status: {_text(audit.get('overall_status'))}\nProcess 1: {_text(p1.get('badge')) or 'Not returned'}\nProcess 2 risk score: {risk_score}/100 ({risk_badge})"),
        _paragraph("Indicators returned by the checker (not independently proven facts):"),
    ])
    rows.extend(_paragraph("• " + flag) for flag in (flags or ["No separate indicator text was returned."]))
    rows.extend([
        _paragraph("7. Transaction / loss information (complete if applicable)", "Heading1"),
        _paragraph("Amount invested or requested: [Complete / None]\nAmount lost or currently at risk: [Complete / None]\nPayment date(s): [Complete]\nRecipient / beneficiary / UPI ID / bank account / wallet: [Complete if known]\nTransaction ID / UTR / payment reference: [Complete]\nSteps taken to contact the entity, bank, platform, or authorities and responses: [Complete]"),
        _paragraph("8. Relief or action requested", "Heading1"),
        _paragraph("I request that the receiving authority, if this matter falls within its remit, assess the attached evidence, verify whether the named person/account/website and any cited SEBI registration are genuinely associated with the relevant regulated entity, and route or advise on the appropriate next step. If I have a direct grievance against a SEBI-regulated entity, I request the applicable grievance-redressal process and a reasoned response. I understand this draft does not itself lodge a complaint or establish fraud."),
        _paragraph("9. Evidence checklist", "Heading1"),
    ])
    evidence_items = []
    if filename:
        evidence_items.append(f"Original uploaded file: {filename} (attach the original separately; this draft does not embed it).")
    evidence_items.extend([
        "Original message / chat export or email with sender details and date/time.",
        "Screenshots or PDFs showing the full communication, account/profile, URLs, and registration claims.",
        "Payment proof, bank statement extract, UTR / transaction receipt, if money was sent.",
        "Copies of prior communications, complaint acknowledgement, and replies, if any.",
        "A record of when each URL was accessed and what it displayed; preserve the original files without editing.",
    ])
    rows.extend(_paragraph("☐ " + item) for item in evidence_items)
    rows.extend([
        _paragraph("10. Declaration", "Heading1"),
        _paragraph("I confirm that I have reviewed this draft, corrected it to reflect what I personally know, distinguished direct observations from suspicion, and attached genuine supporting records to the best of my knowledge. I understand the screening result is not an official SEBI verification or legal determination. I request that the authority verify the facts within its jurisdiction."),
        _paragraph("Signature: ______________________________    Date: __________________\nPlace: _________________________________"),
        _paragraph("11. Filing route and SCORES 2.0 reference", "Heading1"),
        _paragraph("Use SCORES for an eligible securities-market grievance against a listed company, SEBI-registered intermediary, or Market Infrastructure Institution. SEBI’s portal says an investor should first approach the concerned entity through its grievance/compliance contact. SCORES is a facilitation mechanism; it is not a general-purpose fraud-tip or law-enforcement portal. SEBI’s FAQ says information about suspected securities-law violations / market intelligence, and complaints about unregistered or unregulated activity, are not SCORES complaints; those tips may be submitted through SEBI’s Market Intelligence portal. Check the current portal instructions and choose the route that matches your facts."),
        _paragraph("SCORES process reference: eligible complaints are routed to the entity; its Action Taken Report is due within 21 calendar days. If dissatisfied, the current FAQ describes first- and second-level review requests within 15 calendar days of the relevant Action Taken Report. The FAQ also lists a one-year period from the cause of action for lodging a complaint and permits up to 10 supporting files with a cumulative maximum of 20 MB. Confirm current rules, eligible complaint scope, upload limits, and deadlines before filing."),
        _paragraph(f"Official SCORES 2.0 portal: {SCORES_URL}\nSEBI SCORES FAQ (scope, mandatory fields, evidence and process): {SCORES_FAQ_URL}\nSEBI Market Intelligence portal: {MI_PORTAL_URL}"),
        _paragraph("Generated by Nivesh Fraud Checker. Please review before use.", bold=True),
    ])
    return _docx(rows)
