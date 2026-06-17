from flask import Flask, render_template, request
from google import genai
from google.genai import types
import json
app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        message = request.form.get('message')
        scam_image = request.files.get('scam_image')
        platform = request.form.get('platform')
        number = request.form.get('number')
        agency = request.form.get('company')
        ai_input = []
        if platform:
            ai_input.append(types.Part.from_text(text=f"Message was sent using {platform}."))
        if number:
            ai_input.append(types.Part.from_text(text=f"The user {number} this number."))
        if agency:
            ai_input.append(types.Part.from_text(text=f"The user {agency} this company."))
        if message:
            ai_input.append(types.Part.from_text(text = message))
        if scam_image and scam_image.filename:
            image_bytes = scam_image.read()
            ai_input.append(
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=scam_image.content_type,
                )
            )
        if ai_input:
            try:
                client = genai.Client(api_key="")
                print(ai_input) # We wanna check if this works, how it looks
                response = client.models.generate_content(
                        model='gemini-3.1-flash-lite',
                        contents=ai_input,
                        config=types.GenerateContentConfig(
                            system_instruction="You are an evidence-driven assistant that assesses whether a message or attached image is likely a scam. Consider message content, sender info, platform, and image. Return a balanced integer 'scam_score' from 0 (not a scam) to 100 (definite scam). If uncertain, reflect that with a mid-range score (e.g., 40–60). Provide 'reason' in 20–50 words summarizing the key evidence and uncertainty, and 'action' in under 20 words advising the user. Output ONLY valid JSON with keys: {'scam_score': int, 'reason': str, 'action': str}. Do not include any extra explanation, markup, or backticks. Avoid defaulting to high scam scores; weigh both indicators and counter-indicators carefully."),
                        )
                            
                clean_txt = response.text.strip().replace("```json", "").replace("```", "")
                data = json.loads(clean_txt)
                scam_score = int(data["scam_score"])
                response_text = f"{data['reason']} {data['action']}"
                status = "You are safe" if scam_score < 50 else "You have been scammed"
                print(response_text)
            except Exception as e:
                response_text = f"An error occurred: {str(e)}"
                scam_score = 0
                status = "Error"
                print(response_text)
        else:
            response_text = "No input provided"
            scam_score = 0
            status = "Error"
            print(response_text)
        return render_template(
            "result.html",
            status=status,
            scam_score=scam_score,
            message=response_text
        )
    return render_template('index.html')

@app.route('/result')
def result():
    return render_template('result.html')

# @app.route('/rreasteregg')
# def rreasteregg():
#     return render_template('rreas# teregg.html')

if __name__ == "__main__":
    app.run(debug=True)
