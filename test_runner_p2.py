from claim_risk_engine import ClaimRiskEngine

def run_p2_tests():
    engine = ClaimRiskEngine()
    test = engine.process_claim("Guaranteed 300% monthly profits!")
    print(f"Process 2 Test Result: {test['badge']} (Score: {test['risk_score']})")

if __name__ == "__main__":
    run_p2_tests()
