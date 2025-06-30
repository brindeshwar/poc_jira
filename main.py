from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, status, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

from langchain_helper import extract_action_items
from jira_helper import create_jira_task, search_jira_tasks, update_jira_task

app = FastAPI(
    title="Jira Task Creator API",
    description="API to generate and create/update JIRA tasks from meeting transcripts using Langchain.",
    version="1.0.0"
)

# Removed TranscriptInput BaseModel, as the transcript will now be sent as a direct string body.
# class TranscriptInput(BaseModel):
#     transcript: str = Field(..., description="The meeting transcript as plain text.")

class TaskStatus(BaseModel):
    summary: str
    status: str
    jira_key: Optional[str] = None
    jira_url: Optional[str] = None
    message: Optional[str] = None

class TaskCreationResponse(BaseModel):
    message: str
    results: List[TaskStatus]

@app.get("/", include_in_schema=False)
def root():
    return (
        "<html><body>"
        "<h2>Jira Task Creator API</h2>"
        "<p>Use <code>/docs</code> for the interactive API documentation.</p>"
        "</body></html>"
    )

@app.post("/create-jira-tasks", response_model=TaskCreationResponse, status_code=status.HTTP_201_CREATED)
async def create_jira_tasks_endpoint(transcript: str = Body(
        ...,
        description="The meeting transcript as plain text.",
        media_type="text/plain" # <-- ADD THIS LINE
    )):
    # The 'transcript' variable now directly holds the string content of the request body.
    processed_tasks_results: List[TaskStatus] = []

    if not transcript.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcript cannot be empty."
        )

    try:
        action_items = extract_action_items(transcript)
        if not action_items:
            return TaskCreationResponse(
                message="No actionable items found in the transcript.",
                results=[]
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error extracting action items from transcript: {str(e)}"
        )

    for item in action_items:
        summary = item.get("summary", "Generated Task (No Summary)")
        description = item.get("description", summary)
        assignee = item.get("assignee")
        due_date = item.get("due_date")

        try:
            matching_jira_tasks = search_jira_tasks(summary_query=summary)

            if matching_jira_tasks:
                matched_task = matching_jira_tasks[0]
                jira_key = matched_task['key']

                update_result = update_jira_task(
                    jira_key=jira_key,
                    summary=summary,
                    description=description,
                    assignee_email=assignee,
                    due_date=due_date
                )
                processed_tasks_results.append(
                    TaskStatus(
                        summary=summary,
                        status="updated",
                        jira_key=update_result.get("jira_key"),
                        jira_url=update_result.get("jira_url"),
                        message=update_result.get("message")
                    )
                )
            else:
                create_result = create_jira_task(
                    summary=summary,
                    description=description,
                    assignee_email=assignee,
                    due_date=due_date
                )
                processed_tasks_results.append(
                    TaskStatus(
                        summary=summary,
                        status="created",
                        jira_key=create_result.get("jira_key"),
                        jira_url=create_result.get("jira_url"),
                        message=create_result.get("message")
                    )
                )

        except Exception as e:
            processed_tasks_results.append(
                TaskStatus(
                    summary=summary,
                    status="failed",
                    message=f"Error processing Jira task: {str(e)}"
                )
            )
            print(f"FAILED TO PROCESS JIRA TASK for '{summary}': {e}")


    total_successes = sum(1 for r in processed_tasks_results if r.status in ["created", "updated"])
    total_failures = sum(1 for r in processed_tasks_results if r.status == "failed")

    overall_message = f"{total_successes} tasks processed successfully ({sum(1 for r in processed_tasks_results if r.status == 'created')} created, {sum(1 for r in processed_tasks_results if r.status == 'updated')} updated)."
    if total_failures > 0:
        overall_message += f" {total_failures} tasks failed."

    return TaskCreationResponse(
        message=overall_message,
        results=processed_tasks_results
    )