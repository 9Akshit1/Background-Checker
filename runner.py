from resume_verification import EnhancedResumeVerifier, PersonInfo, VerifierConfig

# Setup
api_keys = VerifierConfig.get_api_keys_from_env()
verifier = EnhancedResumeVerifier(api_keys)

# Create person information
person = PersonInfo(
    name="Kyan Chiang",
    region="Toronto, Ontario", 
    school="University of Western Ontario",
    work_experiences=[
        {"company": "Forum Ventures", "role": "Venture Capital Analyst"},
        {"company": "Good News Ventures", "role": "Investment Associate"}
    ],
    #date_of_birth="1985-03-15",  # Optional but recommended
    supervisor_contacts={
        "Microsoft Canada": "jane.smith@microsoft.com",
        "RBC Royal Bank": "bob.wilson@rbc.com"
    }
)

# Run verification
results = verifier.verify_person(person)

# Report will be automatically saved as 'verification_report_John_Doe_YYYYMMDD_HHMMSS.txt'
print(f"Verification completed with {results.confidence_score:.1%} confidence")
print(f"Report saved with {len(results.verification_sources)} sources checked")