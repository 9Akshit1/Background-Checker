import requests
import json
import time
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional
import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
from datetime import datetime
import re

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class PersonInfo:
    name: str
    region: str
    school: str
    work_experiences: List[Dict[str, str]]
    supervisor_contacts: Optional[Dict[str, str]] = None
    date_of_birth: Optional[str] = None  # For criminal background checks
    ssn_last_4: Optional[str] = None     # Optional, for better matching

@dataclass
class VerificationResult:
    school_verification: Dict[str, any]
    work_verification: List[Dict[str, any]]
    social_media_findings: Dict[str, List[str]]
    criminal_background_check: Dict[str, any]
    prepared_emails: List[str]
    confidence_score: float
    verification_sources: List[str]
    report_summary: str

class EnhancedResumeVerifier:
    def __init__(self, api_keys: Dict[str, str] = None):
        """
        Initialize with API keys for various services
        api_keys should contain:
        - 'serp_api': SerpApi key for Google search
        - 'rapidapi': RapidAPI key for various APIs
        - 'hunter': Hunter.io API for company verification
        - 'clearbit': Clearbit API for company information
        - 'pipl': Pipl API for people search
        - 'truthfinder': TruthFinder API for background checks
        """
        self.api_keys = api_keys or {}
        self.session = requests.Session()
        self.verification_sources = []
        
    def search_with_serpapi(self, query: str, num_results: int = 10) -> List[Dict[str, str]]:
        """Use SerpApi for reliable Google search results"""
        if 'serp_api' not in self.api_keys:
            logger.warning("No SerpApi key provided - using fallback method")
            return self._fallback_search(query, num_results)
        
        try:
            url = "https://serpapi.com/search"
            params = {
                'q': query,
                'api_key': self.api_keys['serp_api'],
                'engine': 'google',
                'num': num_results,
                'gl': 'ca',  # Canada results
                'hl': 'en'   # English language
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            for result in data.get('organic_results', []):
                results.append({
                    'title': result.get('title', ''),
                    'url': result.get('link', ''),
                    'snippet': result.get('snippet', '')
                })
                
            logger.info(f"SerpApi found {len(results)} results for: {query}")
            return results
            
        except Exception as e:
            logger.error(f"SerpApi search failed: {e}")
            return self._fallback_search(query, num_results)

    def verify_company_comprehensive(self, company_name: str, domain: str = None) -> Dict[str, any]:
        """
        Comprehensive company verification using multiple sources
        """
        verification_results = {
            'verified': False,
            'confidence': 0.0,
            'sources': [],
            'company_info': {'name': company_name}
        }
        
        # Method 1: Hunter.io verification
        hunter_result = self._verify_with_hunter(company_name, domain)
        if hunter_result['verified']:
            verification_results['confidence'] += 0.3
            verification_results['sources'].append('Hunter.io')
            verification_results['company_info'].update(hunter_result.get('company_info', {}))
        
        # Method 2: Search for company official website
        website_result = self._verify_company_website(company_name)
        if website_result['verified']:
            verification_results['confidence'] += 0.25
            verification_results['sources'].append('Official Website')
            verification_results['company_info'].update(website_result.get('company_info', {}))
        
        # Method 3: Better Business Bureau search
        bbb_result = self._search_bbb(company_name)
        if bbb_result['found']:
            verification_results['confidence'] += 0.15
            verification_results['sources'].append('Better Business Bureau')
            verification_results['company_info']['bbb_rating'] = bbb_result.get('rating')
        
        # Method 4: SEC filings search (for public companies)
        sec_result = self._search_sec_filings(company_name)
        if sec_result['found']:
            verification_results['confidence'] += 0.2
            verification_results['sources'].append('SEC Filings')
            verification_results['company_info']['public_company'] = True
        
        # Method 5: Companies House search (for UK companies)
        if 'uk' in company_name.lower() or 'ltd' in company_name.lower():
            ch_result = self._search_companies_house(company_name)
            if ch_result['found']:
                verification_results['confidence'] += 0.2
                verification_results['sources'].append('Companies House UK')
        
        # Method 6: Crunchbase verification
        crunchbase_result = self._search_crunchbase(company_name)
        if crunchbase_result['found']:
            verification_results['confidence'] += 0.1
            verification_results['sources'].append('Crunchbase')
        
        verification_results['verified'] = verification_results['confidence'] > 0.4
        self.verification_sources.extend(verification_results['sources'])
        
        return verification_results

    def _verify_with_hunter(self, company_name: str, domain: str = None) -> Dict[str, any]:
        """Verify company using Hunter.io API"""
        if 'hunter' not in self.api_keys:
            return {'verified': False, 'reason': 'No Hunter.io API key'}
        
        try:
            if not domain:
                domain = self._guess_company_domain(company_name)
            
            url = "https://api.hunter.io/v2/domain-search"
            params = {
                'domain': domain,
                'api_key': self.api_keys['hunter'],
                'limit': 10
            }
            
            response = self.session.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('data'):
                    company_data = data['data']
                    return {
                        'verified': True,
                        'company_info': {
                            'name': company_data.get('organization'),
                            'domain': company_data.get('domain'),
                            'industry': company_data.get('industry'),
                            'country': company_data.get('country'),
                            'employee_estimate': company_data.get('emails', 0)
                        }
                    }
            
            return {'verified': False, 'reason': 'Company not found in Hunter.io'}
                
        except Exception as e:
            logger.error(f"Hunter.io verification failed: {e}")
            return {'verified': False, 'reason': f'Hunter.io error: {str(e)}'}

    def _verify_company_website(self, company_name: str) -> Dict[str, any]:
        """Verify company by finding official website"""
        try:
            search_query = f'"{company_name}" official website'
            search_results = self.search_with_serpapi(search_query, 5)
            
            official_websites = []
            for result in search_results:
                url = result.get('url', '').lower()
                title = result.get('title', '').lower()
                
                # Look for official website indicators
                if any(indicator in url for indicator in ['.com', '.org', '.net', '.co', '.ca']) and \
                   any(word in title for word in company_name.lower().split()):
                    official_websites.append({
                        'url': result['url'],
                        'title': result['title']
                    })
            
            return {
                'verified': len(official_websites) > 0,
                'company_info': {
                    'official_websites': official_websites[:3]
                }
            }
            
        except Exception as e:
            return {'verified': False, 'reason': f'Website search error: {str(e)}'}

    def _search_bbb(self, company_name: str) -> Dict[str, any]:
        """Search Better Business Bureau for company"""
        try:
            search_query = f'"{company_name}" site:bbb.org'
            search_results = self.search_with_serpapi(search_query, 3)
            
            bbb_found = any('bbb.org' in r.get('url', '') for r in search_results)
            
            rating = None
            if bbb_found and search_results:
                # Try to extract rating from snippet
                for result in search_results:
                    snippet = result.get('snippet', '')
                    rating_match = re.search(r'([A-F][+-]?)\s*rating', snippet, re.IGNORECASE)
                    if rating_match:
                        rating = rating_match.group(1)
                        break
            
            return {
                'found': bbb_found,
                'rating': rating,
                'results': search_results[:2] if bbb_found else []
            }
            
        except Exception as e:
            return {'found': False, 'error': str(e)}

    def _search_sec_filings(self, company_name: str) -> Dict[str, any]:
        """Search SEC EDGAR database for public company filings"""
        try:
            search_query = f'"{company_name}" site:sec.gov'
            search_results = self.search_with_serpapi(search_query, 3)
            
            sec_found = any('sec.gov' in r.get('url', '') for r in search_results)
            
            return {
                'found': sec_found,
                'filings': search_results[:2] if sec_found else []
            }
            
        except Exception as e:
            return {'found': False, 'error': str(e)}

    def _search_companies_house(self, company_name: str) -> Dict[str, any]:
        """Search UK Companies House for company registration"""
        try:
            search_query = f'"{company_name}" site:find-and-update.company-information.service.gov.uk'
            search_results = self.search_with_serpapi(search_query, 3)
            
            ch_found = any('company-information.service.gov.uk' in r.get('url', '') for r in search_results)
            
            return {
                'found': ch_found,
                'registration': search_results[:2] if ch_found else []
            }
            
        except Exception as e:
            return {'found': False, 'error': str(e)}

    def _search_crunchbase(self, company_name: str) -> Dict[str, any]:
        """Search Crunchbase for company information"""
        try:
            search_query = f'"{company_name}" site:crunchbase.com'
            search_results = self.search_with_serpapi(search_query, 2)
            
            cb_found = any('crunchbase.com' in r.get('url', '') for r in search_results)
            
            return {
                'found': cb_found,
                'profile': search_results[:1] if cb_found else []
            }
            
        except Exception as e:
            return {'found': False, 'error': str(e)}

    def verify_education_comprehensive(self, person_info: PersonInfo) -> Dict[str, any]:
        """
        Comprehensive education verification using multiple sources
        """
        verification_results = {
            'verified': False,
            'confidence': 0.0,
            'sources': [],
            'evidence': []
        }
        
        # Method 1: Alumni directories and graduation lists
        alumni_result = self._search_alumni_records(person_info)
        if alumni_result['found']:
            verification_results['confidence'] += 0.4
            verification_results['sources'].append('Alumni Records')
            verification_results['evidence'].extend(alumni_result['evidence'])
        
        # Method 2: Academic publications and research
        academic_result = self._search_academic_publications(person_info)
        if academic_result['found']:
            verification_results['confidence'] += 0.3
            verification_results['sources'].append('Academic Publications')
            verification_results['evidence'].extend(academic_result['evidence'])
        
        # Method 3: University news and press releases
        news_result = self._search_university_news(person_info)
        if news_result['found']:
            verification_results['confidence'] += 0.2
            verification_results['sources'].append('University News')
            verification_results['evidence'].extend(news_result['evidence'])
        
        # Method 4: Professional licensing boards (if applicable)
        license_result = self._search_professional_licenses(person_info)
        if license_result['found']:
            verification_results['confidence'] += 0.3
            verification_results['sources'].append('Professional Licensing')
            verification_results['evidence'].extend(license_result['evidence'])
        
        verification_results['verified'] = verification_results['confidence'] > 0.3
        self.verification_sources.extend(verification_results['sources'])
        
        return verification_results

    def _search_alumni_records(self, person_info: PersonInfo) -> Dict[str, any]:
        """Search for alumni records and graduation announcements"""
        queries = [
            f'"{person_info.name}" "{person_info.school}" graduate alumni',
            f'"{person_info.name}" "{person_info.school}" degree graduation',
            f'{person_info.name} {person_info.school} alumni directory'
        ]
        
        all_evidence = []
        for query in queries:
            results = self.search_with_serpapi(query, 3)
            for result in results:
                if self._is_education_relevant(result, person_info.name, person_info.school):
                    all_evidence.append(result)
            time.sleep(1)
        
        return {
            'found': len(all_evidence) > 0,
            'evidence': all_evidence
        }

    def _search_academic_publications(self, person_info: PersonInfo) -> Dict[str, any]:
        """Search for academic publications and research papers"""
        queries = [
            f'"{person_info.name}" "{person_info.school}" research paper',
            f'"{person_info.name}" "{person_info.school}" publication thesis',
            f'{person_info.name} {person_info.school} site:researchgate.net OR site:scholar.google.com'
        ]
        
        all_evidence = []
        for query in queries:
            results = self.search_with_serpapi(query, 3)
            for result in results:
                if any(site in result.get('url', '') for site in ['researchgate', 'scholar.google', 'academia.edu']):
                    all_evidence.append(result)
            time.sleep(1)
        
        return {
            'found': len(all_evidence) > 0,
            'evidence': all_evidence
        }

    def _search_university_news(self, person_info: PersonInfo) -> Dict[str, any]:
        """Search university news and press releases"""
        school_domain = self._guess_school_domain(person_info.school)
        queries = [
            f'"{person_info.name}" site:{school_domain}',
            f'"{person_info.name}" "{person_info.school}" graduation ceremony',
            f'"{person_info.name}" "{person_info.school}" dean\'s list honor'
        ]
        
        all_evidence = []
        for query in queries:
            results = self.search_with_serpapi(query, 3)
            all_evidence.extend(results)
            time.sleep(1)
        
        return {
            'found': len(all_evidence) > 0,
            'evidence': all_evidence
        }

    def _search_professional_licenses(self, person_info: PersonInfo) -> Dict[str, any]:
        """Search for professional licenses and certifications"""
        # Common professional licensing sites
        license_sites = [
            'site:cpacanada.ca',  # Canadian CPAs
            'site:peo.on.ca',     # Professional Engineers Ontario
            'site:lsac.on.ca',    # Law Society
            'site:cpso.on.ca',    # College of Physicians
        ]
        
        all_evidence = []
        for site in license_sites:
            query = f'"{person_info.name}" {site}'
            results = self.search_with_serpapi(query, 2)
            all_evidence.extend(results)
            time.sleep(1)
        
        return {
            'found': len(all_evidence) > 0,
            'evidence': all_evidence
        }

    def criminal_background_check(self, person_info: PersonInfo) -> Dict[str, any]:
        """
        Comprehensive criminal background check using multiple sources
        """
        background_results = {
            'clean_record': True,
            'confidence': 0.0,
            'sources_checked': [],
            'findings': [],
            'warnings': []
        }
        
        # Method 1: Court records search
        court_result = self._search_court_records(person_info)
        background_results['sources_checked'].append('Court Records')
        if court_result['found']:
            background_results['clean_record'] = False
            background_results['findings'].extend(court_result['findings'])
        
        # Method 2: Sex offender registry
        sex_offender_result = self._search_sex_offender_registry(person_info)
        background_results['sources_checked'].append('Sex Offender Registry')
        if sex_offender_result['found']:
            background_results['clean_record'] = False
            background_results['findings'].extend(sex_offender_result['findings'])
        
        # Method 3: Bankruptcy records
        bankruptcy_result = self._search_bankruptcy_records(person_info)
        background_results['sources_checked'].append('Bankruptcy Records')
        if bankruptcy_result['found']:
            background_results['findings'].extend(bankruptcy_result['findings'])
        
        # Method 4: Professional sanctions
        sanctions_result = self._search_professional_sanctions(person_info)
        background_results['sources_checked'].append('Professional Sanctions')
        if sanctions_result['found']:
            background_results['findings'].extend(sanctions_result['findings'])
        
        # Method 5: News articles about legal issues
        news_result = self._search_legal_news(person_info)
        background_results['sources_checked'].append('Legal News')
        if news_result['found']:
            background_results['findings'].extend(news_result['findings'])
        
        # Calculate confidence based on sources checked
        background_results['confidence'] = min(len(background_results['sources_checked']) / 5.0, 1.0)
        
        # Add warning if person matching is uncertain
        if not person_info.date_of_birth and not person_info.ssn_last_4:
            background_results['warnings'].append(
                "Person matching may be uncertain without DOB or SSN - results may include other individuals with same name"
            )
        
        self.verification_sources.extend(background_results['sources_checked'])
        return background_results

    def _search_court_records(self, person_info: PersonInfo) -> Dict[str, any]:
        """Search public court records"""
        queries = [
            f'"{person_info.name}" court records {person_info.region}',
            f'"{person_info.name}" criminal case {person_info.region}',
            f'"{person_info.name}" arrest {person_info.region}'
        ]
        
        findings = []
        for query in queries:
            results = self.search_with_serpapi(query, 3)
            for result in results:
                if any(keyword in result.get('snippet', '').lower() for keyword in 
                      ['court', 'criminal', 'arrest', 'conviction', 'sentenced']):
                    findings.append({
                        'type': 'Court Record',
                        'source': result['url'],
                        'description': result['snippet']
                    })
            time.sleep(1)
        
        return {
            'found': len(findings) > 0,
            'findings': findings
        }

    def _search_sex_offender_registry(self, person_info: PersonInfo) -> Dict[str, any]:
        """Search sex offender registries"""
        # Canadian sex offender registry is not public, but we can search news
        queries = [
            f'"{person_info.name}" sex offender registry {person_info.region}',
            f'"{person_info.name}" sexual offense {person_info.region}'
        ]
        
        findings = []
        for query in queries:
            results = self.search_with_serpapi(query, 2)
            for result in results:
                if any(keyword in result.get('snippet', '').lower() for keyword in 
                      ['sex offender', 'sexual offense', 'registry']):
                    findings.append({
                        'type': 'Sex Offender Registry',
                        'source': result['url'],
                        'description': result['snippet']
                    })
            time.sleep(1)
        
        return {
            'found': len(findings) > 0,
            'findings': findings
        }

    def _search_bankruptcy_records(self, person_info: PersonInfo) -> Dict[str, any]:
        """Search bankruptcy records"""
        queries = [
            f'"{person_info.name}" bankruptcy {person_info.region}',
            f'"{person_info.name}" insolvency {person_info.region}'
        ]
        
        findings = []
        for query in queries:
            results = self.search_with_serpapi(query, 2)
            for result in results:
                if any(keyword in result.get('snippet', '').lower() for keyword in 
                      ['bankruptcy', 'insolvency', 'creditor', 'debt']):
                    findings.append({
                        'type': 'Bankruptcy Record',
                        'source': result['url'],
                        'description': result['snippet']
                    })
            time.sleep(1)
        
        return {
            'found': len(findings) > 0,
            'findings': findings
        }

    def _search_professional_sanctions(self, person_info: PersonInfo) -> Dict[str, any]:
        """Search for professional sanctions or disciplinary actions"""
        queries = [
            f'"{person_info.name}" professional discipline {person_info.region}',
            f'"{person_info.name}" license revoked suspended {person_info.region}',
            f'"{person_info.name}" ethics violation {person_info.region}'
        ]
        
        findings = []
        for query in queries:
            results = self.search_with_serpapi(query, 2)
            for result in results:
                if any(keyword in result.get('snippet', '').lower() for keyword in 
                      ['disciplinary', 'sanction', 'license', 'ethics', 'violation']):
                    findings.append({
                        'type': 'Professional Sanction',
                        'source': result['url'],
                        'description': result['snippet']
                    })
            time.sleep(1)
        
        return {
            'found': len(findings) > 0,
            'findings': findings
        }

    def _search_legal_news(self, person_info: PersonInfo) -> Dict[str, any]:
        """Search news articles for legal issues"""
        queries = [
            f'"{person_info.name}" lawsuit {person_info.region}',
            f'"{person_info.name}" legal trouble {person_info.region}',
            f'"{person_info.name}" fraud charges {person_info.region}'
        ]
        
        findings = []
        for query in queries:
            results = self.search_with_serpapi(query, 2)
            for result in results:
                if any(keyword in result.get('snippet', '').lower() for keyword in 
                      ['lawsuit', 'legal', 'charges', 'fraud', 'crime']):
                    findings.append({
                        'type': 'Legal News',
                        'source': result['url'],
                        'description': result['snippet']
                    })
            time.sleep(1)
        
        return {
            'found': len(findings) > 0,
            'findings': findings
        }

    def generate_verification_report(self, person_info: PersonInfo, results: VerificationResult) -> str:
        """Generate a comprehensive verification report"""
        
        report_lines = [
            "=" * 80,
            f"BACKGROUND VERIFICATION REPORT",
            "=" * 80,
            f"Subject: {person_info.name}",
            f"Region: {person_info.region}",
            f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "EXECUTIVE SUMMARY",
            "-" * 40,
            f"Overall Confidence Score: {results.confidence_score:.1%}",
            f"Verification Status: {'VERIFIED' if results.confidence_score > 0.6 else 'PARTIAL' if results.confidence_score > 0.3 else 'UNVERIFIED'}",
            ""
        ]

        # Education Verification
        report_lines.extend([
            "EDUCATION VERIFICATION",
            "-" * 40,
            f"School: {person_info.school}",
            f"Verified: {'YES' if results.school_verification.get('verified', False) else 'NO'}",
            f"Confidence: {results.school_verification.get('confidence', 0):.1%}",
            f"Sources Used: {', '.join(results.school_verification.get('sources', []))}",
            ""
        ])

        # Work Experience Verification
        report_lines.extend([
            "WORK EXPERIENCE VERIFICATION",
            "-" * 40
        ])
        
        for i, work_verify in enumerate(results.work_verification):
            company = work_verify.get('company', 'Unknown')
            role = work_verify.get('role', 'Unknown')
            verified = work_verify.get('verified', False)
            confidence = work_verify.get('confidence', 0)
            
            report_lines.extend([
                f"Position {i+1}:",
                f"  Company: {company}",
                f"  Role: {role}",
                f"  Verified: {'YES' if verified else 'NO'}",
                f"  Confidence: {confidence:.1%}",
                f"  Sources: {', '.join(work_verify.get('sources', []))}",
                ""
            ])

        # Criminal Background Check
        bg_check = results.criminal_background_check
        report_lines.extend([
            "CRIMINAL BACKGROUND CHECK",
            "-" * 40,
            f"Clean Record: {'YES' if bg_check.get('clean_record', True) else 'NO'}",
            f"Sources Checked: {', '.join(bg_check.get('sources_checked', []))}",
            f"Confidence: {bg_check.get('confidence', 0):.1%}",
            ""
        ])

        if bg_check.get('findings'):
            report_lines.append("Findings:")
            for finding in bg_check['findings']:
                report_lines.append(f"  - {finding.get('type', 'Unknown')}: {finding.get('description', 'No description')}")
            report_lines.append("")

        if bg_check.get('warnings'):
            report_lines.append("Warnings:")
            for warning in bg_check['warnings']:
                report_lines.append(f"  - {warning}")
            report_lines.append("")

        # Social Media Findings
        report_lines.extend([
            "SOCIAL MEDIA VERIFICATION",
            "-" * 40
        ])
        
        for platform, profiles in results.social_media_findings.items():
            if profiles:
                report_lines.append(f"{platform.title()}: {len(profiles)} profile(s) found")
                for profile in profiles[:3]:  # Limit to first 3
                    report_lines.append(f"  - {profile}")
            else:
                report_lines.append(f"{platform.title()}: No profiles found")
        report_lines.append("")

        # Verification Sources Summary
        unique_sources = list(set(results.verification_sources))
        report_lines.extend([
            "VERIFICATION SOURCES USED",
            "-" * 40,
            f"Total Sources: {len(unique_sources)}",
            "Sources: " + ", ".join(unique_sources),
            "",
            "RECOMMENDATIONS",
            "-" * 40
        ])

        # Add recommendations based on confidence score
        if results.confidence_score > 0.8:
            report_lines.append("✓ High confidence verification - Candidate information appears authentic")
        elif results.confidence_score > 0.6:
            report_lines.append("⚠ Good verification - Most information verified, minor gaps present")
        elif results.confidence_score > 0.3:
            report_lines.append("⚠ Partial verification - Significant information gaps, further verification recommended")
        else:
            report_lines.append("✗ Low confidence - Unable to verify most claims, manual verification strongly recommended")

        report_lines.extend([
            "",
            "NEXT STEPS",
            "-" * 40,
            "1. Contact provided references directly",
            "2. Request official transcripts/diplomas for education verification",
            "3. Perform employment verification calls to HR departments",
            "4. Consider professional background check service for criminal records",
            "",
            "=" * 80,
            f"End of Report - Generated by Enhanced Resume Verifier v2.0",
            "=" * 80
        ])

        return "\n".join(report_lines)

    def save_report_to_file(self, report_content: str, filename: str = "report.txt"):
        """Save the verification report to a text file"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report_content)
            logger.info(f"Report saved to {filename}")
            return True
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
            return False

    def verify_person(self, person_info: PersonInfo) -> VerificationResult:
        """Main verification function with comprehensive checks"""
        logger.info(f"Starting comprehensive verification for {person_info.name}")
        
        # Reset verification sources for this person
        self.verification_sources = []
        
        # School verification
        school_verification = self.verify_education_comprehensive(person_info)
        
        # Work verification
        work_verifications = []
        for work_exp in person_info.work_experiences:
            verification = self._verify_work_comprehensive(person_info, work_exp)
            work_verifications.append(verification)
        
        # Criminal background check
        criminal_check = self.criminal_background_check(person_info)
        
        # Social media verification (broader than just LinkedIn)
        social_media_findings = self._comprehensive_social_search(person_info)
        
        # Email templates
        prepared_emails = self._prepare_emails(person_info)
        
        # Calculate overall confidence
        school_conf = school_verification.get('confidence', 0)
        work_conf = sum(w.get('confidence', 0) for w in work_verifications) / len(work_verifications) if work_verifications else 0
        social_conf = self._calculate_social_confidence(social_media_findings)
        criminal_conf = criminal_check.get('confidence', 0)
        
        # Weight the confidence scores
        overall_confidence = (
            school_conf * 0.3 +  # 30% weight for education
            work_conf * 0.4 +    # 40% weight for work experience
            social_conf * 0.2 +  # 20% weight for social media presence
            criminal_conf * 0.1  # 10% weight for background check completeness
        )
        
        # Create verification result
        result = VerificationResult(
            school_verification=school_verification,
            work_verification=work_verifications,
            social_media_findings=social_media_findings,
            criminal_background_check=criminal_check,
            prepared_emails=prepared_emails,
            confidence_score=overall_confidence,
            verification_sources=list(set(self.verification_sources)),
            report_summary=""
        )
        
        # Generate comprehensive report
        report_content = self.generate_verification_report(person_info, result)
        result.report_summary = report_content
        
        # Save report to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"verification_report_{person_info.name.replace(' ', '_')}_{timestamp}.txt"
        self.save_report_to_file(report_content, filename)
        
        return result

    def _verify_work_comprehensive(self, person_info: PersonInfo, work_exp: Dict[str, str]) -> Dict[str, any]:
        """Comprehensive work verification using multiple sources"""
        company = work_exp['company']
        role = work_exp['role']
        
        # Company verification
        company_verification = self.verify_company_comprehensive(company)
        
        # Search for person at company through multiple channels
        person_work_verification = self._search_person_at_company(person_info, company, role)
        
        # Search professional networks beyond LinkedIn
        professional_verification = self._search_professional_networks(person_info, company, role)
        
        # Combine all verification results
        confidence = 0.0
        sources = []
        evidence = []
        
        if company_verification.get('verified'):
            confidence += 0.4
            sources.extend(company_verification.get('sources', []))
        
        if person_work_verification.get('found'):
            confidence += 0.4
            sources.extend(person_work_verification.get('sources', []))
            evidence.extend(person_work_verification.get('evidence', []))
        
        if professional_verification.get('found'):
            confidence += 0.2
            sources.extend(professional_verification.get('sources', []))
            evidence.extend(professional_verification.get('evidence', []))
        
        return {
            'company': company,
            'role': role,
            'verified': confidence > 0.5,
            'confidence': min(confidence, 1.0),
            'sources': list(set(sources)),
            'evidence': evidence,
            'company_verification': company_verification
        }

    def _search_person_at_company(self, person_info: PersonInfo, company: str, role: str) -> Dict[str, any]:
        """Search for evidence of person working at company"""
        queries = [
            f'"{person_info.name}" "{company}" {role}',
            f'"{person_info.name}" "{company}" employee',
            f'{person_info.name} {company} team member',
            f'"{person_info.name}" "{company}" staff directory'
        ]
        
        all_evidence = []
        sources = []
        
        for query in queries:
            results = self.search_with_serpapi(query, 3)
            for result in results:
                if self._is_work_relevant(result, person_info.name, company, role):
                    all_evidence.append(result)
                    
                    # Identify source type
                    url = result.get('url', '').lower()
                    if 'linkedin' in url:
                        sources.append('LinkedIn')
                    elif company.lower().replace(' ', '') in url:
                        sources.append('Company Website')
                    elif any(site in url for site in ['crunchbase', 'bloomberg', 'reuters']):
                        sources.append('Business Directory')
                    else:
                        sources.append('Web Search')
            time.sleep(1)
        
        return {
            'found': len(all_evidence) > 0,
            'evidence': all_evidence,
            'sources': list(set(sources))
        }

    def _search_professional_networks(self, person_info: PersonInfo, company: str, role: str) -> Dict[str, any]:
        """Search professional networks beyond LinkedIn"""
        professional_sites = [
            'site:indeed.com',
            'site:glassdoor.com',
            'site:xing.com',
            'site:researchgate.net',
            'site:academia.edu',
            'site:behance.net',
            'site:dribbble.com',
            'site:github.com'
        ]
        
        all_evidence = []
        sources = []
        
        for site in professional_sites:
            query = f'"{person_info.name}" "{company}" {site}'
            results = self.search_with_serpapi(query, 2)
            
            for result in results:
                if any(word in result.get('snippet', '').lower() for word in company.lower().split()):
                    all_evidence.append(result)
                    
                    # Extract platform name
                    if 'indeed.com' in result['url']:
                        sources.append('Indeed')
                    elif 'glassdoor.com' in result['url']:
                        sources.append('Glassdoor')
                    elif 'github.com' in result['url']:
                        sources.append('GitHub')
                    # Add other platforms as needed
            
            time.sleep(1)
        
        return {
            'found': len(all_evidence) > 0,
            'evidence': all_evidence,
            'sources': list(set(sources))
        }

    def _comprehensive_social_search(self, person_info: PersonInfo) -> Dict[str, List[str]]:
        """Comprehensive social media search across multiple platforms"""
        platforms = {
            'linkedin': 'site:linkedin.com/in',
            'facebook': 'site:facebook.com',
            'twitter': 'site:twitter.com OR site:x.com',
            'instagram': 'site:instagram.com',
            'youtube': 'site:youtube.com',
            'github': 'site:github.com',
            'medium': 'site:medium.com',
            'personal_websites': f'"{person_info.name}" personal website blog'
        }
        
        findings = {}
        
        for platform, search_term in platforms.items():
            query = f'"{person_info.name}" {search_term}'
            results = self.search_with_serpapi(query, 3)
            
            platform_urls = []
            for result in results:
                url = result.get('url', '')
                if self._is_person_match(result, person_info.name):
                    platform_urls.append(url)
            
            findings[platform] = platform_urls
            time.sleep(1)
        
        return findings

    def _calculate_social_confidence(self, social_findings: Dict[str, List[str]]) -> float:
        """Calculate confidence based on social media presence"""
        total_profiles = sum(len(profiles) for profiles in social_findings.values())
        professional_profiles = len(social_findings.get('linkedin', [])) + len(social_findings.get('github', []))
        
        # Higher weight for professional profiles
        confidence = min((professional_profiles * 0.3 + total_profiles * 0.1), 1.0)
        return confidence

    def _is_person_match(self, result: Dict, name: str) -> bool:
        """Check if search result likely matches the target person"""
        text = f"{result.get('title', '')} {result.get('snippet', '')}".lower()
        name_words = name.lower().split()
        
        # Check if at least 2 name components match (for common names)
        matches = sum(1 for word in name_words if word in text and len(word) > 2)
        return matches >= 2 or (len(name_words) == 1 and name_words[0] in text)

    def _guess_school_domain(self, school_name: str) -> str:
        """Guess school domain for targeted searches"""
        # Remove common school suffixes
        clean_name = school_name.lower()
        suffixes = ['university', 'college', 'institute', 'school']
        
        for suffix in suffixes:
            clean_name = clean_name.replace(f' {suffix}', '').replace(f'{suffix} ', '')
        
        # Replace spaces and common abbreviations
        domain_guess = clean_name.replace(' ', '').replace('&', 'and') + '.edu'
        
        # Handle Canadian schools
        if any(word in school_name.lower() for word in ['toronto', 'mcgill', 'ubc', 'waterloo']):
            domain_guess = domain_guess.replace('.edu', '.ca')
        
        return domain_guess

    def _guess_company_domain(self, company_name: str) -> str:
        """Guess company domain for Hunter.io search"""
        clean_name = company_name.lower()
        suffixes = ['inc', 'corp', 'corporation', 'company', 'co', 'llc', 'ltd', 'ventures', 'venture', 'capital']
        
        for suffix in suffixes:
            clean_name = clean_name.replace(f' {suffix}', '').replace(f'{suffix} ', '')
        
        domain_guess = clean_name.replace(' ', '') + '.com'
        return domain_guess

    def _fallback_search(self, query: str, num_results: int) -> List[Dict[str, str]]:
        """Fallback search method using DuckDuckGo Instant Answer API"""
        try:
            url = "https://api.duckduckgo.com/"
            params = {
                'q': query,
                'format': 'json',
                'no_html': '1',
                'skip_disambig': '1'
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            for result in data.get('Results', [])[:num_results]:
                if result.get('FirstURL'):
                    results.append({
                        'title': result.get('Text', ''),
                        'url': result.get('FirstURL', ''),
                        'snippet': result.get('Text', '')
                    })
            
            for topic in data.get('RelatedTopics', [])[:num_results-len(results)]:
                if isinstance(topic, dict) and topic.get('FirstURL'):
                    results.append({
                        'title': topic.get('Text', ''),
                        'url': topic.get('FirstURL', ''),
                        'snippet': topic.get('Text', '')
                    })
            
            logger.info(f"Fallback search found {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Fallback search failed: {e}")
            return []

    def _is_education_relevant(self, result: Dict, name: str, school: str) -> bool:
        """Check if search result is relevant to education verification"""
        text = f"{result.get('title', '')} {result.get('snippet', '')}".lower()
        name_words = name.lower().split()
        school_words = school.lower().split()
        
        name_match = any(word in text for word in name_words if len(word) > 2)
        school_match = any(word in text for word in school_words if len(word) > 3)
        
        return name_match and school_match

    def _is_work_relevant(self, result: Dict, name: str, company: str, role: str) -> bool:
        """Check if search result is relevant to work verification"""
        text = f"{result.get('title', '')} {result.get('snippet', '')}".lower()
        name_words = name.lower().split()
        company_words = company.lower().split()
        
        name_match = any(word in text for word in name_words if len(word) > 2)
        company_match = any(word in text for word in company_words if len(word) > 2)
        
        return name_match and company_match

    def _prepare_emails(self, person_info: PersonInfo) -> List[str]:
        """Prepare verification email templates"""
        emails = []
        
        # Education verification email
        email = f"""
Subject: Education Verification Request - {person_info.name}

Dear Registrar's Office,

I am conducting an education verification for {person_info.name} who has listed {person_info.school} as their educational institution.

Could you please confirm the following information:
1. Enrollment dates at {person_info.school}
2. Degree(s) obtained and graduation date
3. Field of study/Major
4. Academic standing (if permissible to share)

This verification is being conducted with the candidate's written consent as part of our standard background check process.

Please let me know if you need any additional documentation or if there are specific procedures I should follow.

Thank you for your assistance.

Best regards,
[Your Name]
[Your Title]
[Your Contact Information]
"""
        emails.append(email.strip())
        
        # Work verification emails
        for work_exp in person_info.work_experiences:
            email = f"""
Subject: Employment Verification Request - {person_info.name}

Dear HR Department / Hiring Manager,

I am conducting employment verification for {person_info.name} who has listed {work_exp['company']} as a previous employer.

Could you please confirm the following information:
1. Employment dates at {work_exp['company']}
2. Position held: {work_exp['role']}
3. Employment status (full-time, part-time, contract)
4. Reason for departure (if permissible to share)
5. Eligibility for rehire (if permissible to share)

This verification is being conducted with the candidate's written consent as part of our standard background check process.

If you have a specific employment verification process or forms that need to be completed, please let me know.

Thank you for your time and assistance.

Best regards,
[Your Name]
[Your Title]
[Your Contact Information]
"""
            emails.append(email.strip())
        
        return emails


# Configuration class for easy setup
class VerifierConfig:
    """Configuration helper for setting up API keys"""
    
    @staticmethod
    def get_api_keys_from_env() -> Dict[str, str]:
        """Load API keys from environment variables"""
        return {
            'serp_api': os.getenv('SERP_API_KEY'),
            'rapidapi': os.getenv('RAPIDAPI_KEY'), 
            'hunter': os.getenv('HUNTER_API_KEY'),
            'clearbit': os.getenv('CLEARBIT_API_KEY'),
            'pipl': os.getenv('PIPL_API_KEY'),
            'truthfinder': os.getenv('TRUTHFINDER_API_KEY')
        }
    
    @staticmethod
    def print_setup_instructions():
        """Print instructions for getting API keys"""
        print("""
ENHANCED API SETUP INSTRUCTIONS:
================================

SEARCH & VERIFICATION APIs:
1. SerpApi (Google Search) - FREE TIER: 100 searches/month
   - Go to: https://serpapi.com/
   - Sign up and get API key
   - Set: SERP_API_KEY=your_key_here

2. Hunter.io (Company & Email Verification) - FREE TIER: 50 requests/month
   - Go to: https://hunter.io/
   - Sign up and get API key
   - Set: HUNTER_API_KEY=your_key_here

PROFESSIONAL VERIFICATION APIs:
3. RapidAPI (Multiple Services) - FREE TIER available
   - Go to: https://rapidapi.com/
   - Search for verification APIs
   - Set: RAPIDAPI_API_KEY=your_key_here

4. Clearbit (Company Information) - FREE TIER: 50 requests/month
   - Go to: https://clearbit.com/
   - Sign up for free tier
   - Set: CLEARBIT_API_KEY=your_key_here

BACKGROUND CHECK APIs (Optional):
5. Pipl (People Search) - PAID SERVICE
   - Go to: https://pipl.com/
   - Professional people search API
   - Set: PIPL_API_KEY=your_key_here

6. TruthFinder API - PAID SERVICE
   - Go to: https://www.truthfinder.com/
   - Background check service
   - Set: TRUTHFINDER_API_KEY=your_key_here

ALTERNATIVE FREE SERVICES:
- Companies House API (UK): https://developer.company-information.service.gov.uk/
- SEC EDGAR API (US): https://www.sec.gov/edgar/sec-api-documentation
- OpenCorporates API: https://api.opencorporates.com/

USAGE EXAMPLE:
==============
from enhanced_resume_verifier import EnhancedResumeVerifier, PersonInfo, VerifierConfig

# Setup
api_keys = VerifierConfig.get_api_keys_from_env()
verifier = EnhancedResumeVerifier(api_keys)

# Create person info
person = PersonInfo(
    name="John Doe",
    region="Ontario, Canada",
    school="University of Toronto",
    work_experiences=[
        {"company": "Tech Corp", "role": "Software Engineer"},
        {"company": "Finance Inc", "role": "Data Analyst"}
    ],
    date_of_birth="1990-01-01",  # Optional, for better criminal record matching
    ssn_last_4="1234"           # Optional, for US residents
)

# Run verification
results = verifier.verify_person(person)

# Report will be automatically saved as 'verification_report_John_Doe_YYYYMMDD_HHMMSS.txt'
print(f"Verification completed with {results.confidence_score:.1%} confidence")
print(f"Report saved with {len(results.verification_sources)} sources checked")
""")


