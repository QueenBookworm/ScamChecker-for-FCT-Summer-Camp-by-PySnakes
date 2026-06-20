from flask import Flask, render_template, request
from google import genai
from google.genai import types
import json
app = Flask(__name__)
history_list = []
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        message = request.form.get('message')
        scam_image = request.files.get('scam_image')
        platform = request.form.get('platform')
        number = request.form.get('number')
        agency = request.form.get('company')
        if not message and not (scam_image and scam_image.filename):
            return render_template("result.html", status="Please enter a message or upload an image.", scam_score=100, color="#f56020")
        else:
            ai_input = []
            if platform:
                ai_input.append(types.Part.from_text(text=f"Message was sent using {platform}."))
            if number:
                ai_input.append(types.Part.from_text(text=f"The user {number} know this number."))
            if agency:
                ai_input.append(types.Part.from_text(text=f"The user {agency} company."))
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
                    print("before response")
                    response = client.models.generate_content(
                            model='gemini-3.1-flash-lite',
                            contents=ai_input,
                            config=types.GenerateContentConfig(
                                system_instruction="""Bạn là trợ lý đánh giá dựa trên bằng chứng để xác định tin nhắn hoặc ảnh đính kèm có khả năng là lừa đảo hay không. Hãy xem xét nội dung tin nhắn, thông tin người gửi, nền tảng và hình ảnh. Trả về 'scam_score' là số nguyên cân bằng từ 0 (không phải lừa đảo) đến 100 (chắc chắn là lừa đảo). Nếu chưa chắc chắn, dùng điểm ở khoảng giữa (ví dụ 40–60). 'reason' phải viết bằng tiếng Việt trong 20–50 từ, tóm tắt bằng chứng chính và mức độ không chắc chắn. 'action' phải viết bằng tiếng Việt, dưới 20 từ, để khuyên người dùng nên làm gì. Luôn trả lời bằng tiếng Việt dù nội dung đầu vào dùng ngôn ngữ nào. Chỉ xuất JSON hợp lệ với các khóa: {'scam_score': int, 'reason': str, 'action': str}. Không thêm giải thích, định dạng Markdown hoặc dấu backtick. Không mặc định chấm điểm lừa đảo cao; hãy cân nhắc kỹ cả dấu hiệu đáng ngờ và dấu hiệu an toàn."""),
                            )
                    print("is this ok?")
                    clean_txt = response.text.strip().replace("```json", "").replace("```", "")
                    data = json.loads(clean_txt)
                    scam_score = int(data["scam_score"])
                    print(scam_score)
                    response_text = f"{data['reason']} {data['action']}"
                    status = "Có vẻ an toàn" if scam_score < 50 else "Có dấu hiệu lừa đảo"
                    color = "#f56020" if scam_score <60 else "#E50B31"
                    print("hey yall")
                    history_list.append({"status":status,
                                    "scam_score":scam_score,
                                    "message":response_text,
                                    "original_message":request.form.get('message'),
                                    "color":color})
                    print(f"LOOOKHEEEEEERE{color}")
                    if len(history_list) > 10:
                        history_list.pop(0)
                except Exception as e:
                    response_text = "Đã xảy ra lỗi, vui lòng thử lại."
                    scam_score = 100
                    status = "Lỗi"
                    color = "#f56020"
            else:
                response_text = "Chưa có nội dung để kiểm tra."
                scam_score = 0
                status = "Có lỗi xảy ra, vui lòng thử lại."
                color = "#f56020"
            return render_template(
                "result.html",
                status=status,
                scam_score=scam_score,
                message=response_text,
                original_message=request.form.get('message'),
                color=color
            )
    return render_template('index.html')

@app.route("/history")
def history():
    return render_template('history.html', history=history_list)

@app.route('/result')
def result():
    return render_template('result.html')

# @app.route('/rreasteregg')
# def rreasteregg():
#     return render_template('rreas# teregg.html')

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
