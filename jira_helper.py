import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from jira import JIRA, JIRAError

class JiraSettings(BaseSettings):

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    jira_url: str
    jira_project_key: str
    jira_email: str
    jira_api_token: str

settings = JiraSettings()

# Global JIRA client instance (lazy initialization)
_jira_client = None

def get_jira_client():

    global _jira_client
    if _jira_client is None:
        options = {'server': settings.jira_url}
        _jira_client = JIRA(options=options, basic_auth=(settings.jira_email, settings.jira_api_token))
    return _jira_client

def create_jira_task(
        summary: str,
        description: str,
        assignee_email: str = None,
        due_date: str = None,
) -> dict:

    jira = get_jira_client()

    issue_dict = {
        'project': {'key': settings.jira_project_key},
        'summary': summary,
        'description': description,
        'issuetype': {'name': 'Task'},
    }

    if assignee_email:
        users = jira.search_users(query=assignee_email, maxResults=1)
        if users:
            issue_dict['assignee'] = {'accountId': users[0].accountId}
        else:
            print(f"Warning: Could not find Jira user with email '{assignee_email}'. Task will be unassigned.")

    if due_date:
        issue_dict['duedate'] = due_date

    new_issue = jira.create_issue(fields=issue_dict)
    return {
        "jira_key": new_issue.key,
        "jira_url": f"{settings.jira_url}/browse/{new_issue.key}",
        "message": f"Jira task '{new_issue.key}' created successfully."
    }

def search_jira_tasks(summary_query: str, project_key: str = None) -> list:

    jira = get_jira_client()
    project_key = project_key if project_key else settings.jira_project_key

    jql_query = f'project = "{project_key}" AND summary ~ "{summary_query}" ORDER BY updated DESC'
    issues = jira.search_issues(jql_query, maxResults=5)

    results = []
    for issue in issues:
        assignee_email = issue.fields.assignee.emailAddress if issue.fields.assignee else None
        due_date = issue.fields.duedate if issue.fields.duedate else None
        results.append({
            "key": issue.key,
            "summary": issue.fields.summary,
            "description": issue.fields.description,
            "assignee": assignee_email,
            "due_date": due_date,
        })
    return results

def update_jira_task(
        jira_key: str,
        summary: str = None,
        description: str = None,
        assignee_email: str = None,
        due_date: str = None,
) -> dict:

    jira = get_jira_client()
    issue = jira.issue(jira_key)

    fields_to_update = {}
    if summary is not None:
        fields_to_update['summary'] = summary
    if description is not None:
        fields_to_update['description'] = description
    if due_date is not None:
        fields_to_update['duedate'] = due_date
    elif issue.fields.duedate is not None:
        fields_to_update['duedate'] = None

    if assignee_email is not None:
        users = jira.search_users(query=assignee_email, maxResults=1)
        if users:
            fields_to_update['assignee'] = {'accountId': users[0].accountId}
        else:
            print(f"Warning: Could not find Jira user with email '{assignee_email}'. Assignee not updated.")

    elif issue.fields.assignee is not None and assignee_email is None:
        fields_to_update['assignee'] = {'accountId': ''}

    if fields_to_update:
        issue.update(fields=fields_to_update)

    return {
        "jira_key": issue.key,
        "jira_url": f"{settings.jira_url}/browse/{issue.key}",
        "message": f"Jira task '{issue.key}' updated successfully."
    }


# if __name__ == "__main__":
#     # --- IMPORTANT: Configure your .env before running this ---
#     # --- Make sure JIRA_URL, JIRA_PROJECT_KEY, JIRA_EMAIL, JIRA_API_TOKEN are set ---
#     from dotenv import load_dotenv
#     load_dotenv() # Load .env for local testing
#
#     # Test create_jira_task
#     print("--- Testing create_jira_task ---")
#     test_summary_create = "New Test Task from Script " + os.urandom(2).hex()
#     test_description_create = "This is a brand new test task created to verify the creation functionality."
#     test_assignee_create = "your.colleague@example.com" # CHANGE THIS to a valid Jira user email
#     test_due_date_create = "2025-12-31"
#
#     try:
#         new_task_result = create_jira_task(test_summary_create, test_description_create, test_assignee_create, test_due_date_create)
#         print(f"CREATED: {new_task_result}")
#         created_key = new_task_result["jira_key"]
#     except JIRAError as e:
#         print(f"CREATE FAILED: {e.text}. Status: {e.status_code}")
#         created_key = None
#     except Exception as e:
#         print(f"CREATE FAILED (unexpected): {e}")
#         created_key = None
#
#     if created_key:
#         # Test search_jira_tasks
#         print("\n--- Testing search_jira_tasks ---")
#         search_query = test_summary_create
#         try:
#             found_tasks = search_jira_tasks(search_query)
#             print(f"FOUND {len(found_tasks)} tasks matching '{search_query}':")
#             for task in found_tasks:
#                 print(f"  Key: {task['key']}, Summary: {task['summary']}, Assignee: {task['assignee']}")
#                 if task['key'] == created_key:
#                     found_task_for_update = task
#         except JIRAError as e:
#             print(f"SEARCH FAILED: {e.text}. Status: {e.status_code}")
#             found_task_for_update = None
#         except Exception as e:
#             print(f"SEARCH FAILED (unexpected): {e}")
#             found_task_for_update = None
#
#
#         # Test update_jira_task
#         if created_key and found_task_for_update:
#             print("\n--- Testing update_jira_task ---")
#             updated_summary = f"UPDATED: {test_summary_create}"
#             updated_description = "This task has been updated to reflect new details."
#             updated_assignee = None # Unassign or set to a different user
#             updated_due_date = "2025-06-15" # Change due date
#
#             try:
#                 update_result = update_jira_task(
#                     jira_key=created_key,
#                     summary=updated_summary,
#                     description=updated_description,
#                     assignee_email=updated_assignee,
#                     due_date=updated_due_date
#                 )
#                 print(f"UPDATED: {update_result}")
#             except JIRAError as e:
#                 print(f"UPDATE FAILED: {e.text}. Status: {e.status_code}")
#             except Exception as e:
#                 print(f"UPDATE FAILED (unexpected): {e}")
#         else:
#             print("Skipping update test as no task was created or found.")
#
#     print("\n--- Done with jira_helper.py tests ---")