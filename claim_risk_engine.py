"""Evidence-aware financial claim risk scoring."""
from __future__ import annotations

import re
import json

from fraud_vision import analyze_evidence


class ClaimRiskEngine:
    def __init__(self, client=None):
        self.client = client

    def analyze_pnl_screenshot(self, image_path: str) -> str:
        return analyze_evidence(file_path=image_path, client=self.client)

    @staticmethod
    def compute_risk_score(text_claim: str, ai_analysis: str | dict = "") -> dict:
        analysis_data = ai_analysis if isinstance(ai_analysis, dict) else {}
        document_text = analysis_data.get("extracted_text", "")
        extracted_claims = analysis_data.get("claims", [])
        claim = "\n".join(str(part) for part in (
            text_claim or "", document_text or "", " ".join(map(str, extracted_claims))
        ) if part).lower()
        analysis = (json.dumps(ai_analysis, ensure_ascii=False) if isinstance(ai_analysis, dict) else str(ai_analysis or "")).lower()
        score = 0
        flags = []

        claim_patterns = (
            (r"\bguaranteed?\b.{0,24}\b(?:returns?|profits?|income|wins?)\b|\b(?:returns?|profits?)\b.{0,24}\bguaranteed?\b", 40, "Promises guaranteed investment returns"),
            (r"\b(?:no risk|risk[- ]free|sure shot|double your money|100\s*%\s*(?:win|profit|return))\b", 40, "Promises risk-free or certain profits"),
            (r"\bunofficial\s+(?:whatsapp\s+)?account\b|\bnot an official account\b", 35, "Message states it is from an unofficial account"),
            (r"\b(?:act now|limited time|only today|available only today|offer available today|immediate purchase|send (?:money|funds|crypto)|pay (?:now|upfront))\b", 20, "Uses urgency or upfront-payment pressure"),
            (r"\b(?:send|share)\s+(?:us\s+)?(?:your\s+)?(?:transaction|payment|transfer)\s+(?:screenshot|proof)\b", 25, "Requests transaction proof after directing a purchase"),
            (r"\b(?:secret tip|insider tip|exclusive signal|whatsapp|telegram)\b", 10, "Uses private-channel or tip-selling language"),
        )
        for pattern, points, description in claim_patterns:
            if re.search(pattern, claim):
                score += points
                flags.append(description)

        percentages = [float(value) for value in re.findall(r"(\d+(?:\.\d+)?)\s*%", claim)]
        for percentage in percentages:
            if percentage >= 50:
                score += 35
                flags.append(f"Unusually high stated return ({percentage:g}%)")
                break
            if percentage >= 25:
                score += 35
                flags.append(f"High projected return ({percentage:g}%) needs strong independent verification")
                break

        negative_ai = any(term in analysis for term in (
            "no clear fraud", "no fraud indicators", "none observed", "no suspicious evidence"
        ))
        if analysis_data and not analysis_data.get("sebi_registration_numbers") and not analysis_data.get("registered_company_names"):
            score += 65
            flags.append("No SEBI registration number or company/adviser name could be read from the evidence")
        for finding in analysis_data.get("red_flags", []):
            if finding and finding.casefold() not in {item.casefold() for item in flags}:
                score += 20
                flags.append(str(finding))
        for anomaly in analysis_data.get("visual_anomalies", []):
            if anomaly:
                score += 30
                flags.append(f"Visual anomaly: {anomaly}")
        if not negative_ai:
            if re.search(r"verdict\s*[\"']?\s*:\s*[\"']?\s*high risk|likely fraud|likely a scam|strong evidence of fraud", analysis):
                score += 65
                flags.append("The extracted document evidence contains multiple strong fraud indicators")
            elif re.search(r"verdict\s*[\"']?\s*:\s*[\"']?\s*suspicious|suspicious indicators|possible scam|possible fraud", analysis):
                score += 30
                flags.append("The extracted document evidence contains suspicious indicators")
            if re.search(r"(?:altered|manipulated|edited|fabricated)\s+(?:p&l|profit|return|screenshot|document|statement)", analysis):
                score += 25
                flags.append("Possible alteration in the supplied evidence")

        score = min(100, score)
        badge = "🔴 HIGH RISK" if score >= 65 else ("🟡 REVIEW CAREFULLY" if score >= 25 else "🟢 NO STRONG RED FLAGS FOUND")
        summary = analysis_data.get("document_summary") if analysis_data else ai_analysis
        return {"risk_score": score, "badge": badge, "detected_flags": flags, "ai_summary": summary or "No document was attached."}

    def process_claim(self, claim_text: str, screenshot_path: str | None = None, ai_analysis: str | dict = "") -> dict:
        if screenshot_path and not ai_analysis:
            ai_analysis = self.analyze_pnl_screenshot(screenshot_path)
        return self.compute_risk_score(claim_text, ai_analysis)
