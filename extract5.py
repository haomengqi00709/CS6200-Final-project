import requests
import xml.etree.ElementTree as ET
import time
import re
import os
import json
from datetime import datetime

def fetch_pmc_ids(query, max_results=5):
    """
    Fetch PMC IDs for open-access articles from PubMed Central.
    """
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pmc",
        "term": query,
        "retmode": "json",
        "retmax": max_results
    }

    try:
        response = requests.get(base_url, params=params)
        
        # Add debug information
        print(f"Status Code: {response.status_code}")
        print(f"Response Text: {response.text[:500]}")  # Print first 500 chars
        print(f"Response Headers: {response.headers}")
        
        if response.status_code != 200:
            print(f"Error: API returned status code {response.status_code}")
            return []
            
        try:
            data = response.json()
            pmc_ids = data.get("esearchresult", {}).get("idlist", [])
            return pmc_ids
        except json.JSONDecodeError as e:
            print(f"JSON Decode Error: {str(e)}")
            print(f"Raw Response: {response.text}")
            return []
            
    except requests.exceptions.RequestException as e:
        print(f"Request Error: {str(e)}")
        return []

def fetch_pmc_full_text(pmc_id):
    """
    Fetch and extract full-text content from PubMed Central (PMC) using PMC ID.
    Also retrieves the article title, journal name, authors, date, abstract, and keywords to use as metadata.
    """
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pmc", "id": pmc_id, "retmode": "xml"}

    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        root = ET.fromstring(response.text)

        # Extract article title
        title_elem = root.find(".//article-title")
        title = title_elem.text if title_elem is not None else f"PMC_{pmc_id}"

        # Extract journal name
        journal_elem = root.find(".//journal-title")
        journal_name = journal_elem.text if journal_elem is not None else "Unknown Journal"

        # Extract authors
        authors = []
        contrib_group = root.find(".//contrib-group")
        if contrib_group is not None:
            for author in contrib_group.findall(".//name"):
                surname = author.find("surname")
                given_names = author.find("given-names")
                if surname is not None and given_names is not None:
                    author_name = f"{given_names.text} {surname.text}"
                    authors.append(author_name)

        # Extract publication date
        pub_date = root.find(".//pub-date")
        date = "Unknown Date"
        if pub_date is not None:
            year = pub_date.find("year")
            month = pub_date.find("month")
            day = pub_date.find("day")
            
            date_parts = []
            if year is not None and year.text:
                date_parts.append(year.text)
            if month is not None and month.text:
                date_parts.append(month.text)
            if day is not None and day.text:
                date_parts.append(day.text)
            
            if date_parts:
                date = "-".join(date_parts)

        # Extract abstract
        abstract = ""
        abstract_elem = root.find(".//abstract")
        if abstract_elem is not None:
            abstract_parts = []
            for p in abstract_elem.findall(".//p"):
                if p.text:
                    abstract_parts.append(p.text.strip())
            abstract = " ".join(abstract_parts)

        # Extract keywords
        keywords = []
        kwd_group = root.find(".//kwd-group")
        if kwd_group is not None:
            for kwd in kwd_group.findall(".//kwd"):
                if kwd.text:
                    keywords.append(kwd.text.strip())

        # Clean title to be used as a file name (remove invalid characters)
        if title is not None:
            clean_title = re.sub(r'[\\/*?:"<>|]', '', title)
        else:
            clean_title = "untitled"

        body = root.find(".//body")  # Locate the article's full text
        
        if body is not None:
            full_text = []
            for sec in body.findall(".//sec"):  # Extract all sections
                title_elem = sec.find("title")
                paragraphs = sec.findall("p")
                
                section_text = ""
                if title_elem is not None and title_elem.text:
                    section_text += f"\n## {title_elem.text.strip()}\n"  # Add section title
                    
                for p in paragraphs:
                    if p.text:  # Check if p.text is not None
                        section_text += p.text.strip() + "\n"
                
                if section_text:  # Only append if the section has content
                    full_text.append(section_text)

            metadata = {
                "title": title,
                "journal": journal_name,
                "authors": authors,
                "date": date,
                "abstract": abstract,
                "keywords": keywords
            }
            return metadata, "\n".join(full_text) if full_text else "No readable text found."
        else:
            return {"title": title, "journal": journal_name, "authors": authors, "date": date, "abstract": abstract, "keywords": keywords}, "Full text not available for this article."
    else:
        return None, "Error retrieving full text."

# Main function to loop through PMC IDs and save the full text
def download_pmc_articles_for_pyserini(query, max_results=5, save_base="PMC_Jsonl"):
    # Generate timestamped save directory
  
    save_dir = f"{save_base}_{timestamp}"

    pmc_ids = fetch_pmc_ids(query, max_results)
    
    if not pmc_ids:
        print("No PMC articles found for this query.")
        return
    
    print(f"Found {len(pmc_ids)} articles. Downloading full text...")

    os.makedirs(save_dir, exist_ok=True)
    jsonl_path = os.path.join(save_dir, "collection.jsonl")

    with open(jsonl_path, "w", encoding="utf-8") as jsonl_file:
        for pmc_id in pmc_ids:
            print(f"Processing PMC ID: {pmc_id}...")
            metadata, full_text = fetch_pmc_full_text(pmc_id)
            
            if metadata is None or "Error" in full_text or "Full text not available" in full_text:
                print(f"Skipping {pmc_id} (Full text not available)")
                continue
            
            doc = {
                "id": f"PMC{pmc_id}",
                "title": metadata["title"],
                "journal": metadata["journal"],
                "authors": metadata["authors"],
                "date": metadata["date"],
                "abstract": metadata["abstract"],
                "keywords": metadata["keywords"],
                "contents": full_text

            }
            
            jsonl_file.write(json.dumps(doc) + "\n")
            print(f"Added to JSONL: PMC{pmc_id}")

            time.sleep(0.34)

    print(f"\n✅ Saved {len(pmc_ids)} entries to: {jsonl_path}")

# # Example Usage
# from pyserini.analysis import Analyzer

# def extract_important_words(query):
#     """
#     Extract important words from a query using Pyserini's analyzer.
#     """
#     analyzer = Analyzer("english")  # Use standard English tokenizer
#     tokens = analyzer.analyze(query)  # Tokenize and normalize the query

#     return tokens  # Returns a list of important words
# import os
# print("JAVA_HOME:", os.environ.get("JAVA_HOME"))
# # Example usage
# query = "nutrition AND cardiovascular health"
# important_words = extract_important_words(query)

# print("Important words:", important_words)

query = "What foods are recommended to manage inflammation?"
from testquery1 import extract_keywords
keywords = extract_keywords(query)
print("Important keywords:", keywords)  # ['foods', 'recommended', 'manage', 'inflammation']
timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# Use the keywords list directly
query_string = " ".join(keywords)  # This will create: "foods recommended manage inflammation"
download_pmc_articles_for_pyserini(query_string, max_results=500)


from create_new_index import run_pyserini_index
input_dir = f"/Users/jasonhao/Desktop/2025 MSAI/CS6200/FinalProject/PMC_Jsonl_{timestamp}/"
output_index = f"/Users/jasonhao/Desktop/2025 MSAI/CS6200/FinalProject/new_index_PMC_Jsonl_{timestamp}"

# Run the index creation
run_pyserini_index(
    input_dir=input_dir,
    output_index=output_index
)


from pyserini.search.lucene import LuceneSearcher
import json
from datetime import datetime
from testquery1 import extract_keywords
import time

def run_search(query, timestamp):
    start_time = time.time()
    
    # ----- Config -----
    INDEX_PATH = f"/Users/jasonhao/Desktop/2025 MSAI/CS6200/FinalProject/new_index_PMC_Jsonl_{timestamp}"
    JSONL_PATH = f"/Users/jasonhao/Desktop/2025 MSAI/CS6200/FinalProject/PMC_Jsonl_{timestamp}/collection.jsonl"
    TOP_K = 100

    # ----- Extract Keywords -----
    keywords = extract_keywords(query)
    print("Important keywords:", keywords)

    # ----- Load metadata -----
    raw_docs = {}
    try:
        with open(JSONL_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                doc = json.loads(line)
                raw_docs[doc['id']] = doc
    except FileNotFoundError:
        print(f"Error: Could not find JSONL file at {JSONL_PATH}")
        return
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in file: {e}")
        return

    # ----- Search -----
    try:
        searcher = LuceneSearcher(INDEX_PATH)
        searcher.set_bm25(k1=0.9, b=0.4)
        hits = searcher.search(" ".join(keywords), TOP_K)
    except Exception as e:
        print(f"Error during search: {e}")
        return

    # ----- Prepare output -----
    results = []
    print(f"\nTop {TOP_K} results for query: '{keywords}'\n")

    for i, hit in enumerate(hits):
        doc_id = hit.docid
        score = hit.score
        data = raw_docs.get(doc_id)

        if data:
            result = {
                "rank": i + 1,
                "doc_id": doc_id,
                "score": score,
                "date": data.get("date", "[No date]"),
                "journal_name": data.get("journal", "[No journal]"),
                "authors": data.get("authors", "[No authors]"),
                "title": data.get("title", "[No title]"),
                "abstract": data.get("abstract", "[No abstract]")
            }
        else:
            result = {
                "rank": i + 1,
                "doc_id": doc_id,
                "score": score,
                "error": "Not found in local data file"
            }

        results.append(result)

        # Print to console
        print(f"{i+1}. DocID: {doc_id} | Score: {score:.4f}")
        if data:
            print(f"   Title: {result['title']}")
            print(f"   Journal: {result['journal_name']}")
            print(f"   Date: {result['date']}")
            print(f"   Abstract: {result['abstract'][:200]}...\n")
        else:
            print("   ⚠️ Not found in local data file.\n")

    # ----- Save results to JSONL -----
    output_file = f"bm25_results_{timestamp}.jsonl"
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            for item in results:
                f.write(json.dumps(item) + "\n")
        print(f"\n✅ Results saved to: {output_file}")
    except Exception as e:
        print(f"Error saving results: {e}")

    end_time = time.time()
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    return results

# Main execution
if __name__ == "__main__":
    start_time = time.time()
    # Your query processing
    query = "Are there any dietary restrictions for people with high cholesterol?"
    keywords = extract_keywords(query)
    print("Important keywords:", keywords)
    
    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # Download articles
    query_string = " ".join(keywords)
    download_pmc_articles_for_pyserini(query_string, max_results=500)
    
    # Create index
    input_dir = f"/Users/jasonhao/Desktop/2025 MSAI/CS6200/FinalProject/PMC_Jsonl_{timestamp}/"
    output_index = f"/Users/jasonhao/Desktop/2025 MSAI/CS6200/FinalProject/new_index_PMC_Jsonl_{timestamp}"
    run_pyserini_index(input_dir=input_dir, output_index=output_index)
    
    # Run search
    results = run_search(query, timestamp)
    end_time = time.time()
    print(f"Time taken: {end_time - start_time:.2f} seconds")
