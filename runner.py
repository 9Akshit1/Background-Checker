from resume_verification import HybridVerifier, PersonInfo

def main():
    """Example usage of the hybrid verifier"""
    
    # Your test case
    person = PersonInfo(
        name="Kyan Chiang",
        region="Toronto, Ontario",
        school="University of Western Ontario",  # Full name often works better
        work_experiences=[
            {"company": "Forum Ventures", "role": "Venture Capital Analyst"},
            {"company": "Good News Ventures", "role": "Investment Associate"}
        ],
        supervisor_contacts={"email": "supervisor@example.com"}
    )
    
    verifier = HybridVerifier()
    
    print("Choose verification method:")
    print("1. Quick URL generation (just get the search links)")
    print("2. Interactive verification (guided manual process)")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == "1":
        verifier.quick_url_generator(person)
    elif choice == "2":
        results = verifier.interactive_verification(person)
    else:
        print("Invalid choice. Generating URLs...")
        verifier.quick_url_generator(person)

if __name__ == "__main__":
    main()