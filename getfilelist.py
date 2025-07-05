import requests
import json

# --- CONFIGURATION ---
WORKSPACE_SLUG = "nrs"  # We discovered this is the correct slug from your test
API_KEY = "GTR5W1A-NW8M0J2-GTKZQS2-VFQHHMY" # Make sure this is still correct
BASE_URL = "http://localhost:3001"
# --- END CONFIGURATION ---

def fetch_documents(base_url, api_key):
    """
    Fetches the list of documents from the AnythingLLM API and returns them as a list of dicts.
    """
    url = f"{base_url}/api/v1/documents"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    data = response.json()
    documents = []
    try:
        local_files = data.get('localFiles', {})
        items = local_files.get('items', [])
        if items and isinstance(items[0], dict) and 'items' in items[0]:
            documents = items[0]['items']
    except Exception as e:
        print(f"Error traversing document structure: {e}")
    return documents

if __name__ == "__main__":
    print(f"Attempting to fetch documents from the correct endpoint: {BASE_URL}/api/v1/documents")
    try:
        documents = fetch_documents(BASE_URL, API_KEY)
        if documents:
            print("\n--- SUCCESS! Found Documents ---")
            print(json.dumps(documents, indent=2))
        else:
            print("\nCould not find documents list in the expected format.")
    except requests.exceptions.HTTPError as e:
        print(f"\n--- HTTP ERROR ---")
        print(f"An HTTP error occurred: {e}")
        print(f"Response Content: {e.response.text if hasattr(e, 'response') and e.response else ''}")
        if hasattr(e, 'response') and e.response and e.response.status_code == 404:
            print("Endpoint not found. Check your BASE_URL and endpoint path.")
        elif hasattr(e, 'response') and e.response and e.response.status_code in [401, 403]:
            print("Authorization error. Is your API Key correct and does it have the right permissions?")
    except requests.exceptions.RequestException as e:
        print(f"\n--- CONNECTION ERROR ---")
        print(f"A connection error occurred: {e}")