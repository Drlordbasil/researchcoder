import os
import json
from dotenv import load_dotenv
from groq import Groq
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading

# Load environment variables from .env file
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

# Initialize the Groq client
client = Groq(api_key=api_key)
MODEL = 'llama3-70b-8192'

# Set up Selenium WebDriver with Chrome
def setup_driver():
    service = ChromeService(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--ignore-certificate-errors')
    options.add_argument('--allow-running-insecure-content')
    driver = webdriver.Chrome(service=service, options=options)
    return driver

# Function for web research using Selenium and BeautifulSoup
def perform_web_research(query):
    driver = setup_driver()
    try:
        url = f"https://www.google.com/search?q={query}"
        driver.get(url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.g"))
        )
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        links = [a['href'] for a in soup.select('div.g a') if a['href'].startswith('http')]
        results = []
        for link in links[:3]:  # Limit to first 3 links for brevity
            driver.get(link)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            page_soup = BeautifulSoup(driver.page_source, 'html.parser')
            page_text = ' '.join([p.get_text() for p in page_soup.find_all('p')])
            results.append(page_text[:500])  # Limit to first 500 characters
        return json.dumps({"query": query, "results": results})
    except Exception as e:
        return json.dumps({"error": str(e)})
    finally:
        driver.quit()

# Function to save a project to a file
def save_project(content, filename):
    try:
        with open(filename, 'w', encoding='utf-8') as file:
            file.write(content)
        return json.dumps({"status": "success", "filename": filename})
    except Exception as e:
        return json.dumps({"error": str(e)})

# Function to run conversation with AI and call functions
def run_conversation(user_prompt, context):
    # Step 1: send the conversation and available functions to the model
    messages = context + [
        {
            "role": "user",
            "content": user_prompt,
        }
    ]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "perform_web_research",
                "description": "Perform web research based on a query",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query for web research",
                        }
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_project",
                "description": "Save a project to a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The content of the project",
                        },
                        "filename": {
                            "type": "string",
                            "description": "The filename to save the project",
                        }
                    },
                    "required": ["content", "filename"],
                },
            },
        }
    ]
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        max_tokens=4096
    )

    response_message = response.choices[0].message
    tool_calls = response_message.tool_calls

    # Step 2: check if the model wanted to call a function
    if tool_calls:
        available_functions = {
            "perform_web_research": perform_web_research,
            "save_project": save_project,
        }
        messages.append(response_message)  # extend conversation with assistant's reply

        # Step 3: call the function
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_to_call = available_functions[function_name]
            function_args = json.loads(tool_call.function.arguments)
            function_response = function_to_call(**function_args)
            messages.append(
                {
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                }
            )  # extend conversation with function response
        
        # Step 4: get a new response from the model where it can see the function response
        second_response = client.chat.completions.create(
            model=MODEL,
            messages=messages
        )
        return second_response.choices[0].message.content, messages

    return response_message.content, messages

# GUI code
def start_agent():
    user_prompt = prompt_entry.get("1.0", tk.END).strip()
    if not user_prompt:
        messagebox.showerror("Error", "Please enter a prompt.")
        return

    output_text.delete("1.0", tk.END)

    def run():
        context = [
            {
                "role": "system",
                "content": "You are a highly skilled AI programmer and web researcher. You can call functions to perform web research, write code, and save projects."
            }
        ]
        try:
            response, updated_context = run_conversation(user_prompt, context)
            output_text.insert(tk.END, response + "\n")

            # Handle continuous conversation
            while True:
                follow_up = messagebox.askyesno("Continue", "Do you want to continue the conversation?")
                if not follow_up:
                    break
                follow_up_prompt = prompt_entry.get("1.0", tk.END).strip()
                if not follow_up_prompt:
                    messagebox.showerror("Error", "Please enter a follow-up prompt.")
                    continue
                response, updated_context = run_conversation(follow_up_prompt, updated_context)
                output_text.insert(tk.END, response + "\n")
        except Exception as e:
            output_text.insert(tk.END, f"Error: {str(e)}\n")

    threading.Thread(target=run).start()

root = tk.Tk()
root.title("AI Programmer and Web Researcher")

tk.Label(root, text="Enter your prompt:").pack(pady=5)
prompt_entry = scrolledtext.ScrolledText(root, width=80, height=10)
prompt_entry.pack(pady=5)

start_button = tk.Button(root, text="Start", command=start_agent)
start_button.pack(pady=10)

tk.Label(root, text="Output:").pack(pady=5)
output_text = scrolledtext.ScrolledText(root, width=80, height=20)
output_text.pack(pady=5)

root.mainloop()
