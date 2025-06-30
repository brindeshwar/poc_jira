import os
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import date, timedelta


from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel as LangchainBaseModel
from langchain_google_genai import ChatGoogleGenerativeAI

from dotenv import load_dotenv
load_dotenv()


class ActionItem(LangchainBaseModel):
    summary: str = Field(description="A concise summary of the action item.")
    description: Optional[str] = Field(None, description="A more detailed description of the action item, if available.")
    assignee: Optional[str] = Field(None, description="The name or email of the person assigned to this action item, if specified in the transcript.")
    due_date: Optional[str] = Field(None, description="The due date for the action item in YYYY-MM-DD format, if mentioned (e.g., 'by end of the week' -> infer a date if possible, otherwise leave null).")

class ActionItems(LangchainBaseModel):
    action_items: List[ActionItem] = Field(description="A list of identified action items from the transcript.")

def _get_date_context() -> dict:

    today = date.today()
    days_until_friday = (4 - today.weekday() + 7) % 7
    if days_until_friday == 0:
        upcoming_friday = today + timedelta(days=7)
    else:
        upcoming_friday = today + timedelta(days=days_until_friday)

    return {
        "today_date": today.strftime('%Y-%m-%d'),
        "upcoming_friday": upcoming_friday.strftime('%Y-%m-%d')
    }

def extract_action_items(transcript: str) -> List[dict]:

    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        raise ValueError("Google API key not found. Please set the GOOGLE_API_KEY environment variable.")

    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0, google_api_key=google_api_key)

    date_context = _get_date_context()


    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", f"""You are an expert assistant for extracting actionable tasks from meeting transcripts.
                     Identify specific action items, who they are assigned to (if mentioned), and any due dates.
                     If no assignee or due date is clearly mentioned, leave that field null.
                     Infer a precise YYYY-MM-DD date if phrases like 'end of week' or 'next week' are used,
                     otherwise leave it null.
                     Today's date is {date_context['today_date']}.
                     The upcoming Friday (end of this week) is {date_context['upcoming_friday']}.
                     Output the results as a JSON array of objects, strictly adhering to the schema provided."""),
            ("human", "Meeting Transcript:\n{transcript}"),
        ]
    )

    chain = prompt | llm.with_structured_output(ActionItems)

    try:
        response = chain.invoke({"transcript": transcript})
        return [item.model_dump() for item in response.action_items]
    except Exception as e:
        print(f"Error during LLM action item extraction: {e}")
        return []

# if __name__ == "__main__":
#     print("Attempting to extract action items from a test transcript...")
#
#     test_transcript_1 = "The UI needs to be updated for better mobile support. Assign Ravi to handle the responsive layout updates. Also, integrate the payment gateway by end of the week. Rajesh will look into Razorpay integration."
#     test_transcript_2 = "We need to review the Q3 budget. Sarah will prepare the slides. No specific deadline mentioned."
#     test_transcript_3 = "Just a general discussion, no action items from this one."
#     test_transcript_4 = "Finalize the client proposal by next Tuesday. John will take care of it."
#     test_transcript_5 = "Launch the new marketing campaign by next Monday. Emily will manage it."
#
#     import json
#
#     print("\n--- Test Transcript 1 ---")
#     action_items_1 = extract_action_items(test_transcript_1)
#     print(json.dumps(action_items_1, indent=2))
#
#     print("\n--- Test Transcript 2 ---")
#     action_items_2 = extract_action_items(test_transcript_2)
#     print(json.dumps(action_items_2, indent=2))
#
#     print("\n--- Test Transcript 3 ---")
#     action_items_3 = extract_action_items(test_transcript_3)
#     print(json.dumps(action_items_3, indent=2))
#
#     print("\n--- Test Transcript 4 ---")
#     action_items_4 = extract_action_items(test_transcript_4)
#     print(json.dumps(action_items_4, indent=2))
#
#     print("\n--- Test Transcript 5 ---")
#     action_items_5 = extract_action_items(test_transcript_5)
#     print(json.dumps(action_items_5, indent=2))
#
#     # IMPORTANT: To test this, make sure your .env has GOOGLE_API_KEY set.
#     # Run: python langchain_helper.py
#
#
# #
