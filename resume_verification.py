import requests
from bs4 import BeautifulSoup
import time
import re
import json
from urllib.parse import quote_plus, urljoin
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import logging
import random

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PersonInfo:
    name: str
    region: str
    school: str
    work_experiences: List[Dict[str, str]]  # [{"company": "...", "role": "..."}]
    supervisor_contacts: Optional[Dict[str, str]] = None  # {"email": "...", "phone": "..."}

@dataclass
class VerificationResult:
    school_verification: Dict[str, any]
    work_verification: List[Dict[str, any]]
    social_media_findings: Dict[str, List[str]]
    prepared_emails: List[str]
    confidence_score: float

class ResumeVerifier:
    def __init__(self):
        self.session = requests.Session()
        # Rotate user agents to appear more human-like
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        ]
        self.session.headers.update({
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
    def search_bing(self, query: str, num_results: int = 10) -> List[Dict[str, str]]:
        """Use Bing search (more permissive than Google/DuckDuckGo)"""
        try:
            # Bing search URL
            url = f"https://www.bing.com/search?q={quote_plus(query)}&count={num_results}"
            
            # Add random delay to appear more human-like
            time.sleep(random.uniform(1, 3))
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            results = []
            # Bing's result selectors
            for result in soup.find_all('li', class_='b_algo')[:num_results]:
                title_elem = result.find('h2')
                link_elem = result.find('a')
                
                if title_elem and link_elem:
                    title = title_elem.get_text().strip()
                    link = link_elem.get('href')
                    if link and title and link.startswith('http'):
                        results.append({'title': title, 'url': link})
                        logger.info(f"Found result: {title[:50]}...")
            
            logger.info(f"Found {len(results)} results for query: {query}")
            return results
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error during search: {e}")
            return []
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
    
    def search_direct_sites(self, person_name: str, additional_terms: str = "") -> List[Dict[str, str]]:
        """Search specific sites directly"""
        results = []
        
        # LinkedIn direct search (more reliable than site: operator)
        try:
            linkedin_query = f"https://www.bing.com/search?q={quote_plus(f'{person_name} {additional_terms} linkedin')}"
            response = self.session.get(linkedin_query, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            for result in soup.find_all('li', class_='b_algo'):
                link_elem = result.find('a')
                title_elem = result.find('h2')
                
                if link_elem and title_elem:
                    url = link_elem.get('href', '')
                    title = title_elem.get_text().strip()
                    
                    if 'linkedin.com' in url and person_name.lower() in title.lower():
                        results.append({'title': title, 'url': url, 'source': 'linkedin'})
                        
            time.sleep(random.uniform(2, 4))
            
        except Exception as e:
            logger.error(f"LinkedIn search error: {e}")
        
        return results
    
    def verify_school_attendance(self, person_name: str, school: str, region: str) -> Dict[str, any]:
        """Verify school attendance through multiple sources"""
        logger.info(f"Verifying school attendance: {person_name} at {school}")
        
        verification = {
            'verified': False,
            'sources': [],
            'confidence': 0.0,
            'evidence': []
        }
        
        # Improved search queries
        queries = [
            f'"{person_name}" "{school}" graduate',
            f'"{person_name}" "{school}" alumni',
            f'"{person_name}" "{school}" degree',
            f'{person_name} {school} student',
            f'{person_name} university western ontario',  # More specific for this case
        ]
        
        evidence_count = 0
        
        for query in queries:
            try:
                logger.info(f"Searching: {query}")
                results = self.search_bing(query, 8)
                
                for result in results:
                    title_lower = result['title'].lower()
                    name_parts = person_name.lower().split()
                    school_keywords = school.lower().split()
                    
                    # Check for name and school matches
                    name_match = any(part in title_lower for part in name_parts if len(part) > 2)
                    school_match = any(keyword in title_lower for keyword in school_keywords if len(keyword) > 3)
                    
                    if name_match and school_match:
                        verification['sources'].append(result['url'])
                        verification['evidence'].append({
                            'type': 'search_result',
                            'title': result['title'],
                            'url': result['url'],
                            'relevance': 'high' if name_match and school_match else 'medium'
                        })
                        evidence_count += 1
                        logger.info(f"Found relevant result: {result['title'][:60]}...")
                
                # Longer delay between searches
                time.sleep(random.uniform(3, 6))
                
            except Exception as e:
                logger.error(f"School verification error for query '{query}': {e}")
        
        # Calculate confidence based on evidence found
        verification['confidence'] = min(evidence_count / 2.0, 1.0)  # More realistic threshold
        verification['verified'] = verification['confidence'] > 0.25
        
        logger.info(f"School verification complete. Evidence count: {evidence_count}, Confidence: {verification['confidence']:.2%}")
        return verification
    
    def verify_work_experience(self, person_name: str, company: str, role: str) -> Dict[str, any]:
        """Verify work experience through multiple sources"""
        logger.info(f"Verifying work experience: {person_name} at {company} as {role}")
        
        verification = {
            'company': company,
            'role': role,
            'verified': False,
            'sources': [],
            'confidence': 0.0,
            'evidence': []
        }
        
        # Improved search queries
        queries = [
            f'"{person_name}" "{company}"',
            f'{person_name} {company} {role}',
            f'"{person_name}" "{company}" employee',
            f'{person_name} forum ventures',  # Specific for this case
            f'{person_name} good news ventures',  # Specific for this case
        ]
        
        evidence_count = 0
        
        for query in queries:
            try:
                logger.info(f"Searching work: {query}")
                results = self.search_bing(query, 8)
                
                for result in results:
                    relevance_score = self._calculate_work_relevance(result, person_name, company, role)
                    
                    if relevance_score > 0.3:  # Lower threshold for better results
                        verification['sources'].append(result['url'])
                        verification['evidence'].append({
                            'type': 'work_mention',
                            'title': result['title'],
                            'url': result['url'],
                            'relevance_score': relevance_score
                        })
                        evidence_count += 1
                        logger.info(f"Found work-related result: {result['title'][:60]}...")
                
                time.sleep(random.uniform(3, 6))
                
            except Exception as e:
                logger.error(f"Work verification error for query '{query}': {e}")
        
        verification['confidence'] = min(evidence_count / 2.0, 1.0)
        verification['verified'] = verification['confidence'] > 0.3
        
        logger.info(f"Work verification complete. Evidence count: {evidence_count}, Confidence: {verification['confidence']:.2%}")
        return verification
    
    def search_linkedin(self, person_name: str, school: str = None, company: str = None) -> List[str]:
        """Search for LinkedIn profiles with improved method"""
        logger.info(f"Searching LinkedIn for: {person_name}")
        
        findings = []
        
        # Use direct site searches
        results = self.search_direct_sites(person_name, f"{school} {company}" if school and company else "")
        
        for result in results:
            if result.get('source') == 'linkedin':
                findings.append(result['url'])
        
        # Additional Bing search specifically for LinkedIn
        try:
            linkedin_query = f'{person_name} site:linkedin.com/in'
            results = self.search_bing(linkedin_query, 5)
            
            for result in results:
                if 'linkedin.com' in result['url'] and result['url'] not in findings:
                    findings.append(result['url'])
                    
        except Exception as e:
            logger.error(f"LinkedIn search error: {e}")
        
        logger.info(f"Found {len(findings)} LinkedIn profiles")
        return list(set(findings))
    
    def search_facebook(self, person_name: str, region: str = None) -> List[str]:
        """Search for Facebook profiles"""
        logger.info(f"Searching Facebook for: {person_name}")
        
        findings = []
        
        try:
            fb_query = f'{person_name} site:facebook.com'
            if region:
                fb_query += f' {region}'
                
            results = self.search_bing(fb_query, 5)
            
            for result in results:
                if 'facebook.com' in result['url']:
                    findings.append(result['url'])
                    
        except Exception as e:
            logger.error(f"Facebook search error: {e}")
        
        logger.info(f"Found {len(findings)} Facebook profiles")
        return list(set(findings))
    
    def find_supervisor_contact(self, company: str, department: str = None) -> Dict[str, str]:
        """Attempt to find supervisor contact information"""
        contacts = {}
        
        # Search for company directory or contact information
        queries = [
            f'"{company}" contact directory',
            f'"{company}" team management',
            f'"{company}" staff directory'
        ]
        
        for query in queries:
            try:
                results = self.search_bing(query, 3)
                for result in results:
                    contacts[result['url']] = "Manual review required"
                
                time.sleep(random.uniform(2, 4))
                
            except Exception as e:
                logger.error(f"Contact search error: {e}")
        
        return contacts
    
    def prepare_verification_email(self, person_name: str, company: str, role: str, 
                                  supervisor_email: str = None) -> str:
        """Prepare email template for supervisor verification"""
        
        email_template = f"""
Subject: Employment Verification Request - {person_name}

Dear Hiring Manager/Supervisor,

I hope this email finds you well. I am writing to request employment verification for {person_name}, who has listed {company} as a previous employer on their resume.

Could you please confirm the following information:

1. Employment Period: When did {person_name} work at {company}?
2. Position Title: Did they hold the position of "{role}" as stated?
3. Job Performance: Would you be able to provide a brief assessment of their work performance?
4. Reason for Leaving: What was the reason for their departure?

This information is being requested as part of our standard background verification process with the candidate's full consent. All information provided will be kept confidential and used solely for employment verification purposes.

Please feel free to contact me if you have any questions or concerns about this request.

Thank you for your time and assistance.

Best regards,
[Your Name]
[Your Title]
[Your Company]
[Your Contact Information]

---
Note: This is a template email. Please review and modify as needed before sending.
Supervisor contact: {supervisor_email if supervisor_email else "Contact information not provided - manual search required"}
"""
        return email_template.strip()
    
    def verify_person(self, person_info: PersonInfo) -> VerificationResult:
        """Main verification function"""
        logger.info(f"Starting verification for {person_info.name}")
        
        # School verification
        school_verification = self.verify_school_attendance(
            person_info.name, person_info.school, person_info.region
        )
        
        # Work experience verification
        work_verifications = []
        for work_exp in person_info.work_experiences:
            verification = self.verify_work_experience(
                person_info.name, work_exp['company'], work_exp['role']
            )
            work_verifications.append(verification)
        
        # Social media search
        linkedin_profiles = self.search_linkedin(
            person_info.name, 
            person_info.school, 
            person_info.work_experiences[0]['company'] if person_info.work_experiences else None
        )
        facebook_profiles = self.search_facebook(person_info.name, person_info.region)
        
        social_media_findings = {
            'linkedin': linkedin_profiles,
            'facebook': facebook_profiles
        }
        
        # Prepare verification emails
        prepared_emails = []
        for work_exp in person_info.work_experiences:
            supervisor_email = None
            if person_info.supervisor_contacts and 'email' in person_info.supervisor_contacts:
                supervisor_email = person_info.supervisor_contacts['email']
            
            email = self.prepare_verification_email(
                person_info.name, work_exp['company'], work_exp['role'], supervisor_email
            )
            prepared_emails.append(email)
        
        # Calculate overall confidence score
        school_confidence = school_verification['confidence']
        work_confidence = sum(w['confidence'] for w in work_verifications) / len(work_verifications) if work_verifications else 0
        social_confidence = min((len(linkedin_profiles) + len(facebook_profiles)) / 3.0, 1.0)
        
        overall_confidence = (school_confidence + work_confidence + social_confidence) / 3.0
        
        logger.info(f"Verification complete. Overall confidence: {overall_confidence:.2%}")
        
        return VerificationResult(
            school_verification=school_verification,
            work_verification=work_verifications,
            social_media_findings=social_media_findings,
            prepared_emails=prepared_emails,
            confidence_score=overall_confidence
        )
    
    def _get_school_domain(self, school: str) -> str:
        """Get likely domain for school"""
        domain_mappings = {
            'university of toronto': 'utoronto.ca',
            'uoft': 'utoronto.ca',
            'university of western': 'uwo.ca',
            'western university': 'uwo.ca',
            'harvard': 'harvard.edu',
            'mit': 'mit.edu',
            'stanford': 'stanford.edu'
        }
        
        school_lower = school.lower()
        for key, domain in domain_mappings.items():
            if key in school_lower:
                return domain
        
        return school.lower().replace(' ', '').replace('university', 'edu').replace('college', 'edu')
    
    def _get_company_domain(self, company: str) -> str:
        """Get likely domain for company"""
        return company.lower().replace(' ', '').replace('inc', '').replace('corp', '') + '.com'
    
    def _calculate_work_relevance(self, result: Dict[str, str], person_name: str, 
                                 company: str, role: str) -> float:
        """Calculate relevance score for work-related search results"""
        title = result['title'].lower()
        url = result.get('url', '').lower()
        
        name_parts = person_name.lower().split()
        company_parts = company.lower().split()
        role_parts = role.lower().split()
        
        score = 0.0
        
        # Check for name matches
        name_matches = sum(1 for part in name_parts if part in title and len(part) > 2)
        if name_matches > 0:
            score += 0.4 * (name_matches / len(name_parts))
        
        # Check for company matches
        company_matches = sum(1 for part in company_parts if part in title and len(part) > 2)
        if company_matches > 0:
            score += 0.4 * (company_matches / len(company_parts))
        
        # Check for role matches
        role_matches = sum(1 for part in role_parts if part in title and len(part) > 2)
        if role_matches > 0:
            score += 0.2 * (role_matches / len(role_parts))
        
        # Bonus for LinkedIn profiles
        if 'linkedin.com' in url:
            score += 0.2
        
        return min(score, 1.0)
    
    def generate_report(self, person_info: PersonInfo, result: VerificationResult) -> str:
        """Generate a comprehensive verification report"""
        report = f"""
RESUME VERIFICATION REPORT
==========================

Candidate: {person_info.name}
Region: {person_info.region}
Date Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}

OVERALL CONFIDENCE SCORE: {result.confidence_score:.2%}

EDUCATION VERIFICATION
----------------------
School: {person_info.school}
Verified: {'YES' if result.school_verification['verified'] else 'NO'}
Confidence: {result.school_verification['confidence']:.2%}
Sources Found: {len(result.school_verification['sources'])}

Evidence:
"""
        
        for evidence in result.school_verification['evidence']:
            report += f"  - {evidence['title']}\n    URL: {evidence['url']}\n"
        
        if not result.school_verification['evidence']:
            report += "  - No direct evidence found in automated search\n"
        
        report += f"""
WORK EXPERIENCE VERIFICATION
-----------------------------
"""
        
        for i, work_verification in enumerate(result.work_verification):
            report += f"""
Experience {i+1}:
Company: {work_verification['company']}
Role: {work_verification['role']}
Verified: {'YES' if work_verification['verified'] else 'NO'}
Confidence: {work_verification['confidence']:.2%}
Sources Found: {len(work_verification['sources'])}

Evidence:
"""
            for evidence in work_verification['evidence']:
                report += f"  - {evidence['title']}\n    URL: {evidence['url']}\n    Relevance: {evidence.get('relevance_score', 'N/A')}\n"
            
            if not work_verification['evidence']:
                report += "  - No direct evidence found in automated search\n"
        
        report += f"""
SOCIAL MEDIA PRESENCE
---------------------
LinkedIn Profiles Found: {len(result.social_media_findings['linkedin'])}
"""
        for profile in result.social_media_findings['linkedin']:
            report += f"  - {profile}\n"
        
        report += f"""
Facebook Profiles Found: {len(result.social_media_findings['facebook'])}
"""
        for profile in result.social_media_findings['facebook']:
            report += f"  - {profile}\n"
        
        report += f"""
PREPARED VERIFICATION EMAILS
-----------------------------
{len(result.prepared_emails)} email(s) prepared for supervisor verification.
See separate email templates below.

RECOMMENDATIONS
---------------
"""
        if result.confidence_score > 0.7:
            report += "- HIGH CONFIDENCE: Multiple sources verify the candidate's claims.\n"
        elif result.confidence_score > 0.4:
            report += "- MODERATE CONFIDENCE: Some verification found, recommend manual review.\n"
        else:
            report += "- LOW CONFIDENCE: Limited verification found, recommend thorough manual investigation.\n"
        
        report += "- Review all provided URLs manually for context and accuracy.\n"
        report += "- Consider contacting provided references and supervisors.\n"
        report += "- This automated check supplements but does not replace human verification.\n"
        report += "- Web scraping results may be limited due to anti-bot measures.\n"
        report += "- Consider using professional background check services for comprehensive verification.\n"
        
        return report