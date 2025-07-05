import os
import requests
import json

print("--- SCRIPT START ---")

# --- START OF CONFIGURATION ---
ANYTHINGLLM_API_URL = "http://localhost:3001"
ANYTHINGLLM_API_KEY = "F9059D8-M95MYES-KHQT4RD-F532PAM"
WORKSPACE_SLUG = "nrs"
LOCAL_FOLDER_PATH = "/Users/simonandrews/Library/CloudStorage/OneDrive-Personal/Documents/Training/Nokia NRS II"
# --- END OF CONFIGURATION ---


def get_anythingllm_documents(base_url, api_key, workspace_slug):
    """
    Retrieves a list of document names from a specific AnythingLLM workspace.
    """
    print("\n[DEBUG] Entering 'get_anythingllm_documents' function...")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    # This endpoint fetches all workspaces
    url = f"{base_url}/api/v1/workspaces"
    print(f"[DEBUG] Attempting to fetch documents from URL: {url}")

    try:
        response = requests.get(url, headers=headers)
        print(f"[DEBUG] API response status code: {response.status_code}")
        response.raise_for_status()

        workspaces = response.json().get('workspaces', [])
        print(f"[DEBUG] Found {len(workspaces)} workspaces in total.")

        target_workspace = None
        for ws in workspaces:
            if ws.get('slug') == workspace_slug:
                target_workspace = ws
                break
        
        if not target_workspace:
            print(f"[ERROR] Could not find a workspace with slug '{workspace_slug}'.")
            return None

        documents = target_workspace.get('documents', [])
        filenames = [doc.get('name') for doc in documents if doc.get('name')]
        print(f"[SUCCESS] Found {len(filenames)} documents in workspace '{workspace_slug}'.")
        return set(filenames)

    except requests.exceptions.RequestException as e:
        print(f"[ERROR] An exception occurred while connecting to the API: {e}")
        return None
    except json.JSONDecodeError:
        print("[ERROR] Could not decode the JSON response from the API.")
        print(f"[DEBUG] Raw response text: {response.text}")
        return None

def get_local_files(folder_path):
    """
    Lists all filenames in a given local directory.
    """
    print("\n[DEBUG] Entering 'get_local_files' function...")
    print(f"[DEBUG] Checking local folder path: {folder_path}")
    try:
        expanded_path = os.path.expanduser(folder_path)
        if not os.path.isdir(expanded_path):
            print(f"[ERROR] The provided path is not a valid directory: {expanded_path}")
            return None

        filenames = [f for f in os.listdir(expanded_path) if os.path.isfile(os.path.join(expanded_path, f))]
        filenames = [f for f in filenames if not f.startswith('.')]
        print(f"[SUCCESS] Found {len(filenames)} files in the local folder.")
        return set(filenames)

    except Exception as e:
        print(f"[ERROR] An exception occurred while reading the local directory: {e}")
        return None

def compare_file_lists():
    """
    Main function to fetch both lists and compare them.
    """
    print("\n[DEBUG] Entering 'compare_file_lists' function...")
    llm_files = get_anythingllm_documents(ANYTHINGLLM_API_URL, ANYTHINGLLM_API_KEY, WORKSPACE_SLUG)
    if llm_files is None:
        print("[DEBUG] Exiting script because document list from AnythingLLM could not be retrieved.")
        return

    print("-" * 20)

    local_files = get_local_files(LOCAL_FOLDER_PATH)
    if local_files is None:
        print("[DEBUG] Exiting script because local file list could not be retrieved.")
        return

    print("-" * 20)
    print("\n--- Comparison Report ---")

    missing_from_llm = local_files - llm_files
    if missing_from_llm:
        print(f"\n[!] {len(missing_from_llm)} files are in your local folder but NOT in the '{WORKSPACE_SLUG}' workspace:")
        for filename in sorted(list(missing_from_llm)):
            print(f"  - {filename}")
    else:
        print(f"\n[✔] All files from the local folder are present in the '{WORKSPACE_SLUG}' workspace.")

    extra_in_llm = llm_files - local_files
    if extra_in_llm:
        print(f"\n[!] {len(extra_in_llm)} files are in the '{WORKSPACE_SLUG}' workspace but NOT in your local folder:")
        for filename in sorted(list(extra_in_llm)):
            print(f"  - {filename}")
    else:
        print(f"\n[✔] All files in the '{WORKSPACE_SLUG}' workspace exist in the local folder.")

    common_files = llm_files.intersection(local_files)
    print(f"\n[*] {len(common_files)} files are correctly present in both locations.")

if __name__ == "__main__":
    compare_file_lists()
    print("\n--- SCRIPT END ---")