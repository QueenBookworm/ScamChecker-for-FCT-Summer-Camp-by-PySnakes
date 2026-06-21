import json
import os
import re
from html import escape

import requests
from flask import Flask, jsonify, render_template, request


app = Flask(__name__)

# Basic limits and trusted reference data used by the backend.
MAX_PROMPT_WORDS = 5000
MAX_PROMPT_CHARS = 5000
LEGAL_TEXT = "ScamCheck là công cụ giáo dục do nhóm học viên phát triển và không thay thế cảnh báo chính thức từ ngân hàng hoặc cơ quan chức năng."
OFFICIAL_DOMAINS = {
    "vietcombank": ["vietcombank.com.vn"],
    "bidv": ["bidv.com.vn"],
    "vietinbank": ["vietinbank.vn"],
    "agribank": ["agribank.com.vn"],
    "momo": ["momo.vn"],
}

# Simple project data lives here so the hackathon app stays in only a few files.
SCAM_LIBRARY = [
    {"group": "Giả ngân hàng", "name": "Khóa tài khoản", "description": "Kẻ lừa đảo giả danh ngân hàng và dọa rằng tài khoản của bác sắp bị khóa. Chúng thường tạo áp lực thời gian rồi gửi một đường link lạ để bác đăng nhập hoặc nhập mã OTP. Bác không nên mở link mà hãy tự vào ứng dụng ngân hàng hoặc gọi số chính thức in trên thẻ để kiểm tra.", "example": "Tài khoản bị khóa, bấm link để xác minh OTP."},
    {"group": "Giả ngân hàng", "name": "Hoàn tiền giả", "description": "Người gửi nói bác được hoàn phí, hoàn tiền mua hàng hoặc nhận khoản chuyển nhầm. Sau đó họ yêu cầu nhập số thẻ, mật khẩu, OTP hoặc đóng một khoản phí nhỏ để nhận tiền. Ngân hàng thật không yêu cầu thông tin bí mật qua link trong tin nhắn, vì vậy bác nên đóng trang và gọi ngân hàng để xác minh.", "example": "Ngân hàng hoàn phí, nhập số thẻ tại link này."},
    {"group": "Giả ngân hàng", "name": "Giao dịch lạ", "description": "Tin nhắn cảnh báo có đăng nhập hoặc giao dịch bất thường nhằm làm bác hoảng sợ. Kẻ xấu thường kèm link giả và yêu cầu xác minh ngay trong vài phút hoặc vài giờ. Bác hãy kiểm tra lịch sử giao dịch trong ứng dụng chính thức, không trả lời tin nhắn và không cung cấp OTP.", "example": "Có đăng nhập lạ, xác minh trong 24 giờ."},
    {"group": "Giả công an", "name": "Dính án", "description": "Kẻ lừa đảo tự xưng là công an, viện kiểm sát hoặc tòa án và nói bác liên quan đến một vụ án. Chúng dùng lời đe dọa, yêu cầu giữ bí mật rồi bắt chuyển tiền vào tài khoản gọi là tài khoản kiểm tra. Cơ quan chức năng không điều tra bằng cách yêu cầu chuyển tiền qua điện thoại, vì vậy bác nên dừng liên lạc và báo cho người thân hoặc công an địa phương.", "example": "Bác liên quan vụ rửa tiền, chuyển tiền để xác minh."},
    {"group": "Giả công an", "name": "Phạt nguội giả", "description": "Tin nhắn thông báo xe của bác có lỗi phạt nguội và yêu cầu nộp tiền qua một đường link. Trang giả có thể đánh cắp thông tin thẻ hoặc dẫn bác đến tài khoản cá nhân để chuyển khoản. Bác nên tự tra cứu trên cổng thông tin chính thức hoặc liên hệ cơ quan giao thông, không thanh toán theo hướng dẫn trong tin nhắn lạ.", "example": "Bấm link nộp phạt nguội ngay hôm nay."},
    {"group": "Giả công an", "name": "Cập nhật định danh", "description": "Người gửi giả danh công an hoặc cơ quan quản lý và yêu cầu cập nhật CCCD, VNeID hoặc thông tin thuê bao. Chúng có thể dọa khóa tài khoản, khóa SIM hoặc phạt tiền nếu bác không thực hiện ngay. Bác chỉ nên cập nhật trên ứng dụng và địa điểm chính thức, tuyệt đối không gửi ảnh giấy tờ hay OTP cho người lạ.", "example": "Cập nhật định danh qua link nếu không bị khóa."},
    {"group": "Trúng thưởng", "name": "Nhận quà", "description": "Kẻ lừa đảo thông báo bác trúng điện thoại, tiền mặt hoặc một món quà có giá trị dù bác không tham gia chương trình. Chúng yêu cầu đóng phí vận chuyển, thuế hoặc phí hồ sơ trước khi nhận quà. Bác không nên chuyển tiền và nên kiểm tra chương trình trên trang chính thức của thương hiệu.", "example": "Bác trúng iPhone, đóng phí vận chuyển để nhận."},
    {"group": "Trúng thưởng", "name": "Tri ân khách hàng", "description": "Tin nhắn mạo danh một thương hiệu quen thuộc và nói bác được chọn tham gia chương trình tri ân. Người gửi thường xin CCCD, địa chỉ, thông tin ngân hàng hoặc yêu cầu thanh toán một khoản nhỏ. Bác hãy liên hệ trực tiếp thương hiệu qua kênh chính thức và không cung cấp dữ liệu cá nhân cho tài khoản lạ.", "example": "Nhận quà tri ân, gửi CCCD để xác minh."},
    {"group": "Trúng thưởng", "name": "Vòng quay may mắn", "description": "Đường link mời bác quay thưởng thường hiển thị kết quả trúng giải lớn để tạo cảm giác may mắn. Sau đó trang web yêu cầu đăng nhập, cung cấp thông tin thẻ hoặc đóng phí nhận thưởng. Bác nên đóng trang vì giải thưởng thật không bắt người nhận cung cấp mật khẩu hoặc chuyển tiền trước.", "example": "Quay số trúng tiền mặt tại đường dẫn này."},
    {"group": "Giả giao hàng", "name": "Thiếu phí ship", "description": "Kẻ xấu giả danh shipper và nói đơn hàng còn thiếu một khoản phí vận chuyển rất nhỏ. Link thanh toán có thể là trang giả dùng để lấy thông tin thẻ, mật khẩu hoặc OTP của bác. Bác nên kiểm tra đơn hàng trong ứng dụng mua sắm và chỉ thanh toán bằng phương thức chính thức đã chọn.", "example": "Đơn hàng thiếu 12.000đ, bấm link thanh toán."},
    {"group": "Giả giao hàng", "name": "Không liên lạc được", "description": "Tin nhắn nói shipper đã gọi nhiều lần nhưng không liên lạc được và đơn hàng sắp bị hoàn. Người gửi tạo áp lực để bác bấm link xác nhận địa chỉ hoặc trả thêm phí giao lại. Bác hãy kiểm tra mã đơn trong ứng dụng hoặc gọi tổng đài của đơn vị vận chuyển thay vì mở link lạ.", "example": "Shipper không gọi được, xác nhận địa chỉ tại link."},
    {"group": "Giả giao hàng", "name": "Hải quan giữ hàng", "description": "Kẻ lừa đảo nói kiện hàng của bác đang bị hải quan giữ và cần nộp phí thông quan gấp. Chúng có thể gửi giấy tờ giả, mã vận đơn giả hoặc tài khoản cá nhân để nhận tiền. Bác nên kiểm tra với đơn vị vận chuyển và cơ quan hải quan qua kênh chính thức trước khi thanh toán bất kỳ khoản nào.", "example": "Kiện hàng bị giữ, chuyển phí thông quan ngay."},
]

SAMPLE_MESSAGES = [
    {"label": "Ngân hàng giả", "text": "Kính gửi quý khách, hệ thống phát hiện tài khoản ngân hàng của quý khách vừa đăng nhập từ một thiết bị lạ và sẽ bị khóa sau 24 giờ. Để tiếp tục sử dụng dịch vụ, vui lòng truy cập http://vietcornbank-secure.com, nhập thông tin đăng nhập và mã OTP để xác minh danh tính. Nếu không hoàn thành ngay hôm nay, toàn bộ giao dịch và số dư trong tài khoản có thể bị tạm ngưng. Nhân viên hỗ trợ sẽ không chịu trách nhiệm nếu quý khách bỏ qua thông báo khẩn cấp này."},
    {"label": "Công an giả", "text": "Chúng tôi là cán bộ thuộc cơ quan điều tra và đang xử lý một vụ án rửa tiền có liên quan đến tài khoản đứng tên bạn. Bạn phải giữ bí mật, không được thông báo cho gia đình và chuyển toàn bộ số tiền vào tài khoản tạm giữ để chứng minh tài sản hợp pháp. Nếu không thực hiện trong hai giờ tới, hồ sơ sẽ được chuyển sang khởi tố và bạn phải chịu trách nhiệm trước pháp luật. Hãy gọi lại số điện thoại trong tin nhắn ngay để được cán bộ hướng dẫn từng bước chuyển khoản."},
    {"label": "Trúng thưởng giả", "text": "Chúc mừng quý khách đã được chọn là người nhận giải thưởng đặc biệt trị giá 50 triệu đồng trong chương trình tri ân khách hàng. Để xác nhận giải, quý khách cần gửi ảnh căn cước công dân và chuyển 300.000 đồng phí hồ sơ trong vòng 30 phút. Sau khi nhận phí, ban tổ chức cam kết chuyển toàn bộ tiền thưởng vào tài khoản ngân hàng của quý khách ngay trong ngày. Nếu quá thời hạn trên, giải thưởng sẽ tự động bị hủy và chuyển cho người nhận khác."},
]

TRAINING_MESSAGES = [
    {"label": "scam", "text": "Tài khoản bị khóa, bấm http://nganhang-vn.com để nhập OTP.", "why": "Link lạ và yêu cầu OTP."},
    {"label": "safe", "text": "Mẹ ơi tối nay con về muộn 30 phút vì kẹt xe.", "why": "Tin nhắn đời thường, không ép bấm link hay gửi tiền."},
    {"label": "scam", "text": "Bác trúng 50 triệu, đóng phí hồ sơ 299.000đ để nhận.", "why": "Trúng thưởng nhưng bắt đóng phí trước."},
    {"label": "safe", "text": "Hóa đơn điện tháng này đã có trên ứng dụng chính thức.", "why": "Không có link lạ hoặc yêu cầu mã bí mật."},
    {"label": "scam", "text": "Công an yêu cầu chuyển tiền để chứng minh trong sạch.", "why": "Cơ quan chức năng không yêu cầu chuyển tiền như vậy."},
    {"label": "safe", "text": "Ngân hàng nhắc không cung cấp OTP cho bất kỳ ai.", "why": "Đây là cảnh báo an toàn."},
    {"label": "scam", "text": "Đơn hàng thiếu phí ship, bấm link lạ để thanh toán.", "why": "Phí nhỏ và link lạ là dấu hiệu thường gặp."},
    {"label": "safe", "text": "Lịch khám của bác là 8 giờ sáng mai tại phòng khám cũ.", "why": "Không yêu cầu thông tin nhạy cảm."},
    {"label": "scam", "text": "Cập nhật CCCD trong 2 giờ nếu không bị khóa SIM.", "why": "Tạo áp lực thời gian và xin dữ liệu cá nhân."},
    {"label": "safe", "text": "Con đã chuyển ảnh gia đình qua Zalo, bác xem khi rảnh.", "why": "Không có lời đe dọa, tiền, OTP, hoặc link lạ."},
]

TRAINING_MESSAGES += [
    {"label": "scam", "text": "Nhấn link nhận quà tri ân, nhập số thẻ và ngày hết hạn.", "why": "Yêu cầu thông tin thẻ qua link lạ là nguy hiểm."},
    {"label": "safe", "text": "Cửa hàng báo đơn của bác sẽ giao chiều nay, không cần thanh toán thêm.", "why": "Không có link lạ hoặc yêu cầu chuyển tiền."},
    {"label": "scam", "text": "Có giao dịch lạ 18 triệu, xác minh ngay tại vietcombank-login.net.", "why": "Tên miền không chính thức và tạo cảm giác hoảng sợ."},
    {"label": "safe", "text": "Cháu gửi bác số điện thoại mới của cô Lan để lưu lại.", "why": "Nội dung bình thường, không yêu cầu hành động rủi ro."},
    {"label": "scam", "text": "Tuyển cộng tác viên online, nạp 500.000đ để mở nhiệm vụ đầu tiên.", "why": "Việc làm yêu cầu nạp tiền trước rất đáng nghi."},
    {"label": "safe", "text": "Bưu tá gọi không được, bác có thể ra cổng nhận hàng khi rảnh.", "why": "Không có link thanh toán hoặc yêu cầu OTP."},
    {"label": "scam", "text": "Bạn bị phạt nguội, bấm link đóng phạt ngay để tránh tăng phí.", "why": "Dọa tăng phí và gửi link đóng phạt không chính thức."},
    {"label": "safe", "text": "Gia đình mình họp lúc 7 giờ tối ở nhà cậu Ba nhé.", "why": "Tin nhắn sinh hoạt gia đình, không có dấu hiệu lừa đảo."},
    {"label": "scam", "text": "Nhân viên ngân hàng cần mã OTP để hủy giao dịch giúp bác.", "why": "Không ai được phép hỏi OTP của bác."},
    {"label": "safe", "text": "Bác nhớ mang căn cước khi đi khám bảo hiểm ngày mai.", "why": "Lời nhắc hợp lý, không yêu cầu gửi ảnh hay mã bí mật."},
    {"label": "scam", "text": "Link bình chọn nhận thưởng: bit.ly/qua-tang-vip, gửi ảnh CCCD để nhận.", "why": "Link rút gọn và yêu cầu CCCD là rủi ro cao."},
    {"label": "safe", "text": "Cô giáo gửi lịch họp phụ huynh trong nhóm lớp.", "why": "Không có chuyển tiền, OTP, hoặc đe dọa."},
    {"label": "scam", "text": "Tài khoản Zalo bị tố cáo, đăng nhập link này để tránh khóa vĩnh viễn.", "why": "Dọa khóa tài khoản và dụ đăng nhập qua link lạ."},
    {"label": "safe", "text": "Ngân hàng thông báo bảo trì hệ thống, khuyên không chia sẻ mật khẩu.", "why": "Tin cảnh báo bảo mật, không xin thông tin của bác."},
    {"label": "scam", "text": "Chuyển 2 triệu vào tài khoản tạm giữ, sau điều tra sẽ hoàn lại.", "why": "Yêu cầu chuyển vào tài khoản tạm giữ là chiêu mạo danh."},
]

HOTLINES = [
    {"type": "bank", "name": "Vietcombank", "phone": "1900545413", "note": "Hỗ trợ khách hàng"},
    {"type": "bank", "name": "BIDV", "phone": "19009247", "note": "Hỗ trợ khách hàng"},
    {"type": "bank", "name": "VietinBank", "phone": "1900558868", "note": "Hỗ trợ khách hàng"},
    {"type": "bank", "name": "Agribank", "phone": "1900558818", "note": "Hỗ trợ khách hàng"},
    {"type": "bank", "name": "Techcombank", "phone": "1800588822", "note": "Hỗ trợ khách hàng"},
    {"type": "bank", "name": "MB Bank", "phone": "1900545426", "note": "Hỗ trợ khách hàng"},
    {"type": "bank", "name": "ACB", "phone": "1900545486", "note": "Hỗ trợ khách hàng"},
    {"type": "bank", "name": "Sacombank", "phone": "1900555588", "note": "Hỗ trợ khách hàng"},
    {"type": "bank", "name": "VPBank", "phone": "1900545415", "note": "Hỗ trợ khách hàng"},
    {"type": "bank", "name": "TPBank", "phone": "1900585885", "note": "Hỗ trợ khách hàng"},
    {"type": "official", "name": "Công an", "phone": "113", "note": "Khẩn cấp"},
    {"type": "official", "name": "Phản ánh cuộc gọi rác/lừa đảo", "phone": "156", "note": "Bộ TT&TT"},
    {"type": "official", "name": "Tin nhắn rác/lừa đảo", "phone": "5656", "note": "Gửi phản ánh SMS"},
]


def load_env():
    """Simple .env loader so students do not need extra setup knowledge."""
    if not os.path.exists(".env"):
        return
    with open(".env", "r", encoding="utf-8-sig") as file:
        for line in file:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip().strip('"').strip("'")


load_env()


def gemini_keys():
    """Return all configured Gemini keys so the app can try the next key."""
    raw = " ".join([
        os.getenv("GEMINI_API_KEY", ""),
        os.getenv("GEMINI_API_KEYS", ""),
        os.getenv("GOOGLE_API_KEY", ""),
    ])
    keys = [key.strip() for key in re.split(r"[\s,;]+", raw) if key.strip()]
    return list(dict.fromkeys(keys))


def gemini_models():
    """Prefer user-configured models, then fall back through known Gemini Flash models."""
    extra_models = re.split(r"[\s,;]+", os.getenv("GEMINI_MODELS", ""))
    models = [
        *extra_models,
        os.getenv("GEMINI_MODEL", ""),
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
    ]
    return [model for model in dict.fromkeys(models) if model]


def clamp(value, fallback=None):
    """Convert a score-like value into a 0-100 integer."""
    try:
        return max(0, min(100, round(float(value))))
    except Exception:
        return fallback


def require_ai_score(data, fallback=None):
    """Read Gemini's risk score and fail loudly unless a fallback is allowed."""
    raw = data.get("riskpercentage", data.get("risk_percentage", data.get("danger_score_percent", data.get("score"))))
    if raw is None:
        if fallback is not None:
            return fallback
        raise ValueError("Gemini không trả riskpercentage.")
    score = clamp(raw, None)
    if score is None:
        if fallback is not None:
            return fallback
        raise ValueError("Gemini trả riskpercentage không hợp lệ.")
    return score


def risk_from_score(score):
    if score >= 76:
        return "danger", "Nguy hiểm"
    if score >= 26:
        return "suspicious", "Nghi ngờ"
    return "safe", "An toàn"


def default_actions(score):
    if score >= 76:
        return [
            {"label": "Không bấm link", "prompt": "Tôi chưa bấm link. Hãy hướng dẫn cách kiểm tra an toàn."},
            {"label": "Gọi nguồn chính thức", "prompt": "Tôi muốn xác minh với ngân hàng hoặc cơ quan chính thức."},
            {"label": "Hỏi người thân", "prompt": "Tôi muốn nhờ người nhà kiểm tra lại trước khi làm tiếp."},
        ]
    if score >= 26:
        return [
            {"label": "Kiểm tra người gửi", "prompt": "Tôi muốn kiểm tra người gửi có thật hay không."},
            {"label": "Không cung cấp OTP", "prompt": "Tôi chưa cung cấp OTP hoặc mật khẩu. Hãy nhắc tôi các điều cần tránh."},
            {"label": "Lưu lại bằng chứng", "prompt": "Tôi muốn lưu tin nhắn này để hỏi người thân hoặc bên hỗ trợ."},
        ]
    return [
        {"label": "Vẫn không gửi OTP", "prompt": "Tin có vẻ an toàn, nhưng hãy nhắc tôi cách giữ an toàn."},
        {"label": "Kiểm tra link nếu có", "prompt": "Hãy hướng dẫn tôi kiểm tra link mà không bấm trực tiếp."},
        {"label": "Lưu kết quả", "prompt": "Tôi muốn lưu kết quả này để xem lại sau."},
    ]


RISKY_HIGHLIGHT_PATTERNS = [
    r"https?://[^\s<>()]+|www\.[^\s<>()]+",
    r"\b[a-z0-9-]+\.[a-z]{2,}(?:/[^\s<>()]*)?",
    r"(?:bấm|nhấn|mở|truy cập|click|open)\s+(?:vào\s+)?(?:đường\s+)?link",
    r"(?:bam|nhan|mo|truy cap)\s+(?:vao\s+)?(?:duong\s+)?link",
    r"(?:nhập|gửi|cung cấp|đọc)\s+(?:mã\s+)?OTP",
    r"(?:nhap|gui|cung cap|doc)\s+(?:ma\s+)?OTP",
    r"(?:nhập|gửi|cung cấp)\s+(?:mật khẩu|mã PIN|CCCD|căn cước|thông tin thẻ)",
    r"(?:nhap|gui|cung cap)\s+(?:mat khau|ma PIN|CCCD|can cuoc|thong tin the)",
    r"(?:chuyển|gửi|nạp|đóng|thanh toán)\s+(?:tiền|phí|khoản)",
    r"(?:chuyen|gui|nap|dong|thanh toan)\s+(?:tien|phi|khoan)",
    r"(?:nhận|receive)\s+(?:tiền|money|thưởng|quà)",
    r"(?:nhan|receive)\s+(?:tien|money|thuong|qua)",
    r"(?:tài khoản|SIM|thẻ).{0,24}(?:bị\s+)?khóa",
    r"(?:tai khoan|SIM|the).{0,24}(?:bi\s+)?khoa",
    r"(?:xác minh|đăng nhập).{0,28}(?:ngay|gấp|trong\s+\d+\s*(?:phút|giờ))",
    r"(?:xac minh|dang nhap).{0,28}(?:ngay|gap|trong\s+\d+\s*(?:phut|gio))",
    r"(?:ngay|gấp|khẩn cấp|trong\s+\d+\s*(?:phút|giờ))",
    r"(?:ngay|gap|khan cap|trong\s+\d+\s*(?:phut|gio))",
]


def add_highlight_span(spans, start, end, text_length):
    if end <= start or end - start < 3:
        return
    # Do not highlight the whole prompt; the yellow should point to specific risk cues.
    if end - start > 120 or end - start > text_length * 0.45:
        return
    spans.append((start, end))


def highlight_original(text, evidence):
    raw_text = str(text or "")
    if not raw_text:
        return ""

    spans = []
    text_length = len(raw_text)

    for pattern in RISKY_HIGHLIGHT_PATTERNS:
        for match in re.finditer(pattern, raw_text, re.I):
            add_highlight_span(spans, match.start(), match.end(), text_length)

    for row in evidence:
        if not isinstance(row, dict):
            continue
        quote = str(row.get("quote", "")).strip()
        if len(quote) < 3:
            continue
        start = raw_text.lower().find(quote.lower())
        if start >= 0:
            add_highlight_span(spans, start, start + len(quote), text_length)

    if not spans:
        return escape(raw_text)

    spans.sort()
    merged = []
    for start, end in spans:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)

    output = []
    cursor = 0
    for start, end in merged:
        output.append(escape(raw_text[cursor:start]))
        output.append(f"<mark>{escape(raw_text[start:end])}</mark>")
        cursor = end
    output.append(escape(raw_text[cursor:]))
    return "".join(output)


def sentence_count(text):
    text = str(text or "").strip()
    if not text:
        return 0
    endings = re.findall(r"[.!。！](?=\s|$)", text)
    return max(1, len(endings))


def detailed_evidence_why(quote, why):
    """Make evidence explanations useful even when Gemini returns a short reason."""
    why = str(why or "").strip()
    if sentence_count(why) >= 4:
        return why

    quote_lower = str(quote or "").lower()
    additions = []

    if re.search(r"https?://|www\.|\b[a-z0-9-]+\.[a-z]{2,}", quote_lower):
        additions.append("Đường dẫn lạ có thể dẫn đến trang giả mạo để lấy mật khẩu, mã OTP hoặc thông tin thẻ.")
    if re.search(r"otp|mật khẩu|mat khau|pin|cccd|căn cước|can cuoc|thông tin thẻ|thong tin the", quote_lower):
        additions.append("Đây là nhóm thông tin nhạy cảm, người lạ hoặc nhân viên thật không nên yêu cầu bác gửi qua tin nhắn.")
    if re.search(r"chuyển|chuyen|gửi|gui|nạp|nap|đóng|dong|thanh toán|thanh toan|tiền|tien|phí|phi|300", quote_lower):
        additions.append("Yêu cầu chuyển tiền hoặc đóng phí trước thường được dùng để chiếm tiền rồi tiếp tục đòi thêm khoản khác.")
    if re.search(r"30 phút|30 phut|ngay|gấp|gap|khẩn cấp|khan cap|quá thời hạn|qua thoi han", quote_lower):
        additions.append("Áp lực thời gian làm người nhận khó bình tĩnh kiểm tra nguồn chính thức trước khi hành động.")
    if re.search(r"hủy|huy|khóa|khoa|mất|mat|phạt|phat", quote_lower):
        additions.append("Lời đe dọa hậu quả khiến bác dễ làm theo hướng dẫn mà chưa kịp hỏi người thân hoặc tổ chức thật.")

    additions.append("Bác nên dừng lại, không làm theo yêu cầu trong tin, rồi tự mở kênh chính thức để kiểm tra.")
    additions.append("Nếu còn phân vân, bác nên hỏi người thân hoặc liên hệ trực tiếp tổ chức thật bằng số điện thoại chính thức.")

    additions.append("Việc kiểm tra chậm lại vài phút thường an toàn hơn nhiều so với làm theo một yêu cầu gấp trong tin nhắn.")

    parts = [why] if why else []
    for sentence in additions:
        if sentence not in parts:
            parts.append(sentence)
        if len(parts) >= 4:
            break
    return " ".join(parts)


def result_html(item):
    """Turn a cleaned Gemini result into the analysis dashboard HTML."""
    score = item["danger_score_percent"]
    risk = item["risk"]
    color = {"safe": "#22c55e", "suspicious": "#f59e0b", "danger": "#ef4444"}.get(risk, "#f59e0b")
    evidence = item.get("evidence", [])
    actions = item.get("next_actions", [])
    original_html = highlight_original(item.get("checked_text", ""), evidence)
    psychology = item.get("psychology")

    def short_support_text(text):
        """Limit the support card to the calm 2-3 sentence shape the UI expects."""
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return " ".join(sentence for sentence in sentences[:3] if sentence).strip()
    if risk == "safe":
        psychology_html = ""
    elif psychology:
        psychology_html = f"""
        <section class="support-card" aria-label="Cô tâm lý nhắc nhẹ">
          <div class="support-icon" aria-hidden="true">♡</div>
          <div>
            <h3>Cô tâm lý nhắc nhẹ</h3>
            <p>{escape(short_support_text(psychology))}</p>
          </div>
        </section>"""
    else:
        psychology_html = """
        <p class="support-note">Cô tâm lý đang bận, bác có thể tiếp tục theo các bước bên trên.</p>"""
    evidence_html = "".join(
        f"<div><strong>{escape(str(row.get('quote', 'Dấu hiệu')))}</strong><p>{escape(str(row.get('why') or row.get('explanation') or ''))}</p></div>"
        for row in evidence[:4] if isinstance(row, dict)
    ) or f"<p>{escape(str(item.get('checked_text', '')))}</p>"
    actions_html = "".join(
        f"<button class='action-btn' data-action='{index}'><span>{escape(action['label'])}</span><span>→</span></button>"
        for index, action in enumerate(actions)
    )
    return f"""
<div id="resultCard" style="--risk-color:{color};padding:18px">
  <section class="result-head"><span class="pill {risk}" id="scorePill">{escape(item['verdict_label'])} · {score}% rủi ro</span><h2>Phân tích kỹ thuật</h2><p class="hint">{escape(item['summary'])}</p><p>{escape(item['explanation'])}</p></section>
  <div class="result-main"><div id="scoreRing" class="ring" style="--score:{score}%"><strong id="scoreText">{score}%</strong><small>rủi ro</small></div><div><h2 id="zoneTitle">{escape(item['zone_title'])}</h2><p class="hint">{escape(item['uncertainty'])}</p></div></div>
  <div class="grid"><div class="box"><h3>Dấu hiệu phát hiện</h3><div class="evidence">{evidence_html}</div></div><div class="box"><h3>Nên làm gì tiếp?</h3><div class="checks">{actions_html}</div></div></div>
  <div class="box original-text"><h3>Tin gốc đã tô vàng</h3><p>{original_html or "Không có văn bản gốc để tô vàng."}</p></div>
  {psychology_html}
</div>"""


def restore_result(data):
    """Convert older local-history formats into the current dashboard format."""
    score = require_ai_score(data)
    risk, label = risk_from_score(score)
    actions = data.get("next_actions", data.get("actions", []))
    return {
        **data,
        "source": "gemini",
        "danger_score_percent": score,
        "risk": data.get("risk") or risk,
        "verdict_label": data.get("verdict_label") or data.get("verdict") or label,
        "zone_title": data.get("zone_title") or data.get("zoneTitle") or label,
        "summary": data.get("summary") or "Kết quả kiểm tra đã lưu",
        "explanation": data.get("explanation") or "Mở lại kết quả đã phân tích trên thiết bị này.",
        "uncertainty": data.get("uncertainty") or "Hãy xác minh qua nguồn chính thức nếu còn lo lắng.",
        "evidence": data.get("evidence") if isinstance(data.get("evidence"), list) else [],
        "next_actions": clean_actions(actions if isinstance(actions, list) else []),
        "checked_text": data.get("checked_text") or data.get("inputText", ""),
    }


def read_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def word_count(text):
    return len(re.findall(r"\S+", str(text or "")))


def too_long_error():
    return jsonify({"error": f"Nội dung quá dài. Vui lòng rút gọn dưới {MAX_PROMPT_WORDS} từ rồi thử lại."}), 400


def prompt_is_too_long(*parts):
    text = " ".join(str(part or "") for part in parts)
    return len(text) > MAX_PROMPT_CHARS or word_count(text) > MAX_PROMPT_WORDS


def extract_links(text):
    pattern = r"(?i)\b(?:https?://|www\.)[^\s<>()]+|\b[a-z0-9-]+\.[a-z]{2,}(?:/[^\s<>()]*)?"
    return [link.rstrip(".,;:!?)]}") for link in re.findall(pattern, str(text or ""))]


def domain_of(link):
    link = link.lower()
    link = re.sub(r"^https?://", "", link)
    link = re.sub(r"^www\.", "", link)
    return link.split("/", 1)[0]


def looks_like_fake_domain(domain):
    compact = re.sub(r"[^a-z0-9]", "", domain.lower())
    warnings = []
    for brand, official in OFFICIAL_DOMAINS.items():
        if any(domain.endswith(real) for real in official):
            continue
        if brand in compact or compact.replace("rn", "m").replace("0", "o").replace("1", "l").find(brand) >= 0:
            warnings.append(f"Tên miền {domain} có thể giả mạo {brand}.")
    shorteners = ("bit.ly", "tinyurl.com", "cutt.ly", "bom.so", "goo.gl", "t.co")
    if domain in shorteners:
        warnings.append(f"Đường dẫn {domain} là link rút gọn, cần kiểm tra trước khi bấm.")
    return warnings


def link_warnings(text):
    links = extract_links(text)
    rows = []
    for link in links:
        domain = domain_of(link)
        for warning in looks_like_fake_domain(domain):
            rows.append({"quote": link, "why": warning})
    return rows


def is_quota_error(text):
    text = str(text).lower()
    return (
        "quota" in text
        or "429" in text
        or "resource_exhausted" in text
        or "rate limit" in text
        or "rate_limit" in text
        or "too many requests" in text
        or "exceeded" in text
        or "limit" in text
    )


def is_key_error(text):
    text = str(text).lower()
    return (
        "api key not valid" in text
        or "unauthenticated" in text
        or "permission_denied" in text
        or "api_key_invalid" in text
    )


def is_model_error(text):
    text = str(text).lower()
    return "is not found for api version" in text or "not_supported" in text or "model not found" in text


def is_temporary_error(text):
    text = str(text).lower()
    return (
        is_quota_error(text)
        or "503" in text
        or "unavailable" in text
        or "timeout" in text
        or "deadline" in text
        or "connection" in text
        or "temporarily" in text
    )


def friendly_gemini_error(error):
    text = str(error)
    if "safety" in text.lower() or "blocked" in text.lower() or "finish_reason" in text.lower():
        return "AI chưa thể phân tích nội dung này. Bác có thể che bớt thông tin riêng tư rồi thử lại."
    if is_quota_error(text):
        return "Gemini đang hết lượt hoặc bị giới hạn tạm thời. Hãy thử lại sau vài phút hoặc thêm Gemini API key khác trong .env."
    if "api key not valid" in text.lower() or "unauthenticated" in text.lower():
        return "Gemini API key chưa hợp lệ. Hãy kiểm tra GEMINI_API_KEY trong file .env."
    if "riskpercentage" in text or "3 bước" in text:
        return "Gemini trả dữ liệu chưa đúng định dạng. Hãy bấm phân tích lại."
    return "Gemini chưa phản hồi được. Hãy thử lại sau."


def parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").replace("json\n", "", 1).strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            return json.loads(match.group(0))
        return {}


def ask_gemini(prompt, image=None):
    """Call Gemini and rotate through available keys/models after errors."""
    keys = gemini_keys()
    if not keys:
        raise RuntimeError("Chua co Gemini API key trong .env")

    parts = [{"text": prompt}]
    if image and image.get("dataUrl") and image.get("mimeType"):
        image_data = image["dataUrl"].split(",", 1)[1]
        parts.append({"inline_data": {"mime_type": image["mimeType"], "data": image_data}})

    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.15},
    }

    last_error = "Gemini chua phan hoi."
    tried = []
    for model in gemini_models():
        for key_index, key in enumerate(keys, start=1):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
            try:
                response = requests.post(url, json=body, timeout=45)
                if response.ok:
                    payload = response.json()
                    candidates = payload.get("candidates", [])
                    if not candidates:
                        raise RuntimeError("AI safety blocked or returned no candidates")
                    text = candidates[0]["content"]["parts"][0]["text"]
                    return parse_json(text)
                last_error = response.text
                tried.append(f"key {key_index}, {model}: HTTP {response.status_code}")
                if is_model_error(last_error):
                    break
                if is_quota_error(last_error) or is_key_error(last_error) or is_temporary_error(last_error):
                    continue
            except Exception as error:
                last_error = str(error)
                tried.append(f"key {key_index}, {model}: {type(error).__name__}")
                continue
    raise RuntimeError(last_error + "\nTried: " + "; ".join(tried[-8:]))


def analysis_prompt(message):
    """Build the main Vietnamese scam-analysis instruction for Gemini."""
    return f"""
Bạn là Thám tử ScamCheck, một nhân vật phân tích lừa đảo với giọng khô khan, lý tính, bình tĩnh.
Chỉ trả về JSON hợp lệ. Viết tiếng Việt có dấu, ngắn gọn, dễ hiểu.
Mọi giá trị người dùng nhìn thấy phải là tiếng Việt, không dùng tiếng Anh.

Mục tiêu demo: phản hồi phải đủ rõ để người lớn tuổi hiểu ngay vì sao nên cẩn thận.
Không làm họ hoảng sợ, không đùa, không phán xét. Hãy nêu bằng chứng, kết luận và bước tiếp theo.

Khi phân tích, hãy xét các nhóm dấu hiệu sau nếu có:
- Ai đang tự nhận là người gửi: ngân hàng, công an, shipper, nhà mạng, người thân, tuyển dụng, trúng thưởng.
- Có tạo áp lực thời gian không: khóa tài khoản, hết hạn, mất tiền, phải làm ngay, trong vài phút/giờ.
- Có yêu cầu hành động nguy hiểm không: bấm link, nhập OTP, mật khẩu, số thẻ, căn cước, chuyển tiền, tải app.
- Link hoặc tên miền có đáng ngờ không: tên miền lạ, sai chính tả, không giống website chính thức.
- Nội dung có thiếu ngữ cảnh không: không ghi tên ngân hàng/công ty cụ thể, lời chào chung chung, văn phong kỳ lạ.
- Nếu là ảnh, hãy đọc chữ trong ảnh rồi phân tích như tin nhắn thật.

Hãy tự chấm riskpercentage từ 0 đến 100 theo chính nội dung người dùng đưa vào.
Không dùng điểm mẫu, không dùng điểm mặc định, không đoán theo ví dụ cũ.
Tin bình thường hoặc có nguồn rõ ràng phải thấp. Tin thiếu ngữ cảnh nên ở mức trung bình.
OTP, mật khẩu, ngân hàng, chuyển tiền gấp, link lạ, giả người thân cấp cứu thì cao.
Tin giao hàng/bưu điện chỉ yêu cầu xác minh chung, không có link, không đòi tiền,
không OTP/mật khẩu thì chưa được xếp nguy hiểm.

Hiệu chỉnh điểm theo hướng dẫn sau, nhưng vẫn phải tự đánh giá toàn bộ ngữ cảnh:
- 0-15: nội dung đời thường hoặc thông báo rõ nguồn, không có link lạ, tiền hay dữ liệu bí mật.
- 16-35: có một chi tiết cần kiểm tra nhưng chưa có yêu cầu nguy hiểm hoặc dấu hiệu lừa đảo rõ.
- 36-60: thiếu ngữ cảnh, người gửi chưa xác minh hoặc có lời thúc giục, nhưng bằng chứng còn chưa đủ.
- 61-80: có nhiều dấu hiệu đáng ngờ như mạo danh, link lạ, đe dọa, hứa thưởng hoặc yêu cầu cung cấp dữ liệu.
- 81-100: yêu cầu chuyển tiền, cung cấp OTP/mật khẩu, cài ứng dụng lạ, hoặc giả cơ quan chức năng để gây áp lực.
Không chọn 50 chỉ vì chưa chắc chắn. Không chọn 90 hoặc 95 theo thói quen. Điểm phải phản ánh số lượng,
mức độ nghiêm trọng và sự kết hợp của các dấu hiệu thật sự xuất hiện trong nội dung hiện tại.
Một từ như "ngân hàng", "giao hàng" hoặc "trúng thưởng" tự nó chưa đủ để kết luận nguy hiểm.
Nếu nội dung chỉ nhắc người dùng không chia sẻ OTP hoặc hướng dẫn mở ứng dụng chính thức thì đó có thể là tin an toàn.

Quy trình suy luận trước khi trả JSON:
1. Xác định người gửi tự nhận là ai và họ muốn người nhận làm gì.
2. Tách dữ kiện có trong tin khỏi những điều chỉ đang suy đoán.
3. Đánh giá từng dấu hiệu: tiền, dữ liệu bí mật, đường link, áp lực thời gian, mạo danh và lời hứa bất thường.
4. Tìm dấu hiệu làm giảm rủi ro, ví dụ không yêu cầu hành động, dùng kênh chính thức hoặc chỉ đưa cảnh báo an toàn.
5. Cân bằng cả dấu hiệu tăng và giảm rủi ro rồi mới chọn một điểm duy nhất từ 0 đến 100.
6. Kiểm tra lại rằng summary, explanation, evidence và next_actions đều phù hợp với chính điểm vừa chọn.

next_actions phải có đúng 3 bước ngắn, cụ thể, phù hợp với chính nội dung vừa kiểm tra.
Không bịa thông tin không có trong nội dung. Nếu chưa chắc, hãy nói rõ phần chưa chắc trong uncertainty.
Không thay người dùng quyết định tài chính; chỉ hướng dẫn cách kiểm tra an toàn.

Yêu cầu chất lượng nội dung:
- summary phải nói thẳng kết luận, không dùng câu chung chung như "hãy cẩn thận".
- explanation phải liên hệ trực tiếp giữa điểm rủi ro và các chi tiết trong tin.
- evidence chỉ chứa dấu hiệu thực sự có trong nội dung; quote phải là đoạn trích nguyên văn ngắn.
- Không tạo evidence cho một dấu hiệu có mức đóng góp bằng 0 hoặc không xuất hiện.
- next_actions phải khác nhau, thực hiện được ngay và sắp theo thứ tự ưu tiên.
- Với tin an toàn, hành động nên tập trung vào xác minh nhẹ nhàng, không được hù dọa hoặc yêu cầu báo công an vô lý.
- Với tin nguy hiểm, ưu tiên dừng tương tác, bảo vệ tài khoản và liên hệ nguồn chính thức.
- Không tự tạo số điện thoại, đường link, tên ngân hàng hoặc cơ quan không có trong nội dung.

Trả về đúng một JSON object, không markdown, gồm các trường:
- riskpercentage: số nguyên do bạn tự chấm từ 0 đến 100.
- summary: 1 câu ngắn nói kết luận chính.
- explanation: 3-5 câu ngắn, nêu vì sao điểm rủi ro như vậy và chi tiết nào ảnh hưởng nhiều nhất.
- uncertainty: 1-2 câu nói phần còn chưa chắc hoặc cần xác minh thêm; nếu không còn điểm chưa chắc, nói rõ điều đó.
- evidence: 2 đến 4 dấu hiệu quan trọng nhất, mỗi mục có quote và why.
- next_actions: đúng 3 bước, mỗi bước có label ngắn và prompt hướng dẫn 1-2 câu.

Nội dung:
{message or "(The user uploaded an image. Read the image and analyze it.)"}
"""


def psychology_prompt(message, detective):
    context = {
        "tin_goc": message,
        "ket_qua_tham_tu": compact_result(detective),
    }
    return f"""
Bạn là Cô tâm lý ScamCheck. Hãy xưng là "cô" và gọi người dùng là "bác".
Giọng gần gũi, bình tĩnh, không hù dọa, không lên giọng dạy dỗ.
Giải thích chiêu thức tâm lý mà kẻ lừa đảo đã dùng trong tin nhắn.
Chỉ trả JSON hợp lệ, không markdown.

Bắt buộc:
- answer gồm đúng 2 đến 3 câu tiếng Việt.
- Không quá dài, không dùng thuật ngữ khó.
- Nếu thông tin chưa chắc, nói nhẹ nhàng là cần kiểm tra thêm.

Bối cảnh:
{json.dumps(context, ensure_ascii=False)}

Trả về JSON object:
- answer: đoạn giải thích 2 đến 3 câu.
"""


def clean_result(data, message):
    """Normalize Gemini JSON into the exact shape expected by the frontend."""
    if not isinstance(data, dict):
        data = {}
    score = require_ai_score(data, fallback=50)
    risk, default_label = risk_from_score(score)
    evidence = data.get("evidence") if isinstance(data.get("evidence"), list) else []

    # Local link checks are deterministic, so show them even if Gemini misses them.
    evidence = [*link_warnings(message), *evidence]
    actions = data.get("next_actions") if isinstance(data.get("next_actions"), list) else []
    cleaned_evidence = []
    for row in evidence[:4]:
        if isinstance(row, dict):
            quote = str(row.get("quote", "")).strip()
            why = str(row.get("why") or row.get("explanation") or "").strip()
            if quote or why:
                cleaned_evidence.append({"quote": quote[:180], "why": detailed_evidence_why(quote, why)[:820]})
    return {
        "source": "gemini",
        "risk": risk,
        "danger_score_percent": score,
        "verdict_label": data.get("verdict_label") or default_label,
        "zone_title": data.get("zone_title") or data.get("zoneTitle") or default_label,
        "summary": data.get("summary") or "Kết quả cần được kiểm tra thêm.",
        "explanation": data.get("explanation") or "AI chưa trả đủ cấu trúc, nên ScamCheck hiển thị mức nghi ngờ mặc định để ứng dụng không bị gãy.",
        "uncertainty": data.get("uncertainty") or "Hãy xác minh qua nguồn chính thức nếu còn lo lắng.",
        "evidence": cleaned_evidence,
        "next_actions": clean_actions(actions, exact_three=True),
        "checked_text": message,
    }


def add_psychology_if_needed(result, message, image=None):
    """Ask for a short empathy-focused explanation only when risk is not safe."""
    if result["risk"] == "safe":
        return result
    try:
        data = ask_gemini(psychology_prompt(message, result), image)
        answer = str(data.get("answer", "")).strip() if isinstance(data, dict) else ""
        result["psychology"] = answer or "Cô thấy tin này dùng cảm giác gấp gáp để bác hành động nhanh. Bác cứ chậm lại và kiểm tra qua nguồn chính thức trước."
    except Exception:
        result["psychology_error"] = "Cô tâm lý đang bận, bác thử lại sau. Phần phân tích kỹ thuật vẫn hiển thị đầy đủ ở trên."
    return result


def clean_actions(actions, exact_three=False):
    """Keep action buttons short and guarantee three buttons for the main result."""
    cleaned = []
    for index, action in enumerate(actions[:4]):
        if isinstance(action, dict):
            label = str(action.get("label", "")).strip()
            prompt = str(action.get("prompt", "")).strip()
        else:
            label = str(action).strip()
            prompt = label
        if label:
            cleaned.append({"id": f"step_{index + 1}", "label": label[:80], "prompt": prompt[:240]})
    if exact_three and len(cleaned) < 3:
        cleaned.extend(default_actions(50)[len(cleaned):])
    if cleaned:
        return cleaned[:3] if exact_three else cleaned
    return default_actions(50) if exact_three else []


def compact_result(item):
    """Keep useful AI context while excluding saved HTML and large browser data."""
    if not isinstance(item, dict):
        return {}
    fields = ("time", "inputText", "danger_score_percent", "verdict_label", "summary",
              "explanation", "uncertainty", "evidence", "next_actions")
    return {name: item.get(name) for name in fields if item.get(name) not in (None, "", [])}


def chat_prompt(data):
    context = {
        "ket_qua_hien_tai": compact_result(data.get("result", {})),
        "lich_su_kiem_tra_tren_thiet_bi": [compact_result(row) for row in data.get("history", [])[:5]],
        "lich_su_chat_gan_day": data.get("messages", [])[-6:],
        "noi_dung_file_text_neu_co": str(data.get("fileText", ""))[:3000],
        "cau_hoi_moi": data.get("question", ""),
    }
    return f"""
Bạn là ScamCheck Chat, trợ lý hỏi đáp tiếp tục sau khi người dùng đã phân tích một tin nhắn/lừa đảo.
Chỉ trả JSON hợp lệ bằng tiếng Việt có dấu, không markdown.

Nhiệm vụ:
- Trả lời câu hỏi mới của người dùng bằng 1-3 đoạn ngắn, dễ hiểu cho người lớn tuổi.
- Nếu người dùng gửi ảnh/file mới, hãy dùng nội dung đó như thông tin cập nhật mới về vụ việc.
- Nếu có rủi ro, nói rõ nên làm gì ngay bây giờ, nhưng không làm người dùng hoảng sợ.
- Không bịa số hotline, số tài khoản, tên cơ quan nếu người dùng không cung cấp. Có thể nhắc gọi ngân hàng qua số chính thức trên thẻ/app hoặc báo cáo 156/5656 khi phù hợp.
- Nếu cần thêm thông tin, hỏi đúng 1 câu ngắn.
- Nếu câu hỏi là về việc đã bấm link, nhập OTP, gửi tiền, gửi CCCD, cài app lạ, hãy ưu tiên hướng dẫn chặn thiệt hại.
- Dùng kết quả hiện tại và lịch sử kiểm tra để hiểu bối cảnh; không bắt người dùng kể lại thông tin đã có.
- Lịch sử này chỉ là dữ liệu cục bộ người dùng vừa gửi trong yêu cầu, không nói rằng có tài khoản hoặc cơ sở dữ liệu đám mây.

Bối cảnh:
{json.dumps(context, ensure_ascii=False)}

Trả về đúng JSON object gồm:
- answer: câu trả lời chính.
- next_steps: danh sách 0 đến 3 bước ngắn, mỗi bước là một chuỗi.
"""


def rescue_prompt(situation, result, hotlines):
    context = {
        "tinh_huong": situation,
        "ket_qua_phan_tich": compact_result(result),
        "danh_sach_so_duoc_phep_dung": hotlines,
    }
    return f"""
Bạn là Người ứng cứu ScamCheck.
Giọng bình tĩnh và dứt khoát. Không an ủi. Không phân tích lại. Không cảm thán.
Chỉ liệt kê bước hành động cụ thể theo tình huống.
Chỉ được dùng số điện thoại có trong danh_sach_so_duoc_phep_dung. Không tự tạo số mới.
Mỗi bước phải có một câu nói mẫu để người dùng đọc khi gọi điện.
Trả JSON hợp lệ, không markdown.

Bối cảnh:
{json.dumps(context, ensure_ascii=False)}

Trả về JSON object:
- steps: danh sách 3 đến 5 chuỗi, đánh số sẵn "1. ..."
"""


def allowed_phone_set():
    return {row["phone"] for row in HOTLINES}


def clean_rescue_steps(raw_steps):
    """Drop rescue advice that invents phone numbers outside the trusted hotline list."""
    phones = allowed_phone_set()
    cleaned = []
    for step in raw_steps if isinstance(raw_steps, list) else []:
        text = str(step).strip()
        found = set(re.findall(r"\b\d{3,11}\b", text))
        if found and not found.issubset(phones):
            continue
        if text:
            cleaned.append(text[:420])
    return cleaned[:5]


# Web pages and API endpoints used by static/app.js.
@app.route("/")
def home():
    return render_template("index.html", samples=SAMPLE_MESSAGES)


@app.route("/api/analyze", methods=["POST"])
def analyze():
    # Text and image inputs both go through the same Gemini prompt so the UI stays simple.
    data = read_body()
    message = str(data.get("message", "")).strip()
    image = data.get("image")
    if not message and not image:
        return jsonify({"error": "Vui long nhap tin nhan, link, giong noi hoac tai anh."}), 400
    if prompt_is_too_long(message):
        return too_long_error()
    try:
        result = clean_result(ask_gemini(analysis_prompt(message), image), message)
        result = add_psychology_if_needed(result, message, image)
        result["html"] = result_html(result)
    except Exception as error:
        return jsonify({
            "error": friendly_gemini_error(error),
            "detail": str(error)[:500],
        }), 503
    return jsonify(result)


@app.route("/api/chat", methods=["POST"])
def chat():
    data = read_body()
    question = str(data.get("question", "")).strip()
    image = data.get("image")
    file_text = str(data.get("fileText", "")).strip()
    if not question and not image and not file_text:
        return jsonify({"error": "Vui long nhap cau hoi hoac tai them anh/file."}), 400
    if prompt_is_too_long(question, file_text):
        return too_long_error()
    try:
        answer = ask_gemini(chat_prompt(data), image)
        return jsonify({
            "source": "gemini",
            "answer": str(answer.get("answer", "")).strip(),
            "next_steps": (answer.get("next_steps") if isinstance(answer.get("next_steps"), list) else [])[:3],
        })
    except Exception as error:
        return jsonify({
            "error": friendly_gemini_error(error),
            "detail": str(error)[:500],
        }), 503


@app.route("/api/library")
def library():
    return jsonify(SCAM_LIBRARY)


@app.route("/api/training")
def training():
    return jsonify(TRAINING_MESSAGES)


@app.route("/api/hotlines")
def hotlines():
    return jsonify(HOTLINES)


@app.route("/api/rescue", methods=["POST"])
def rescue():
    # Rescue mode is allowed to fall back locally because users may need urgent steps.
    data = read_body()
    raw_situations = data.get("situations")
    situations = [str(value).strip() for value in raw_situations] if isinstance(raw_situations, list) else [str(data.get("situation", "")).strip()]
    situations = list(dict.fromkeys(value for value in situations if value))
    result = data.get("result", {})
    if situations == ["none"]:
        return jsonify({
            "source": "local",
            "steps": ["Bác làm rất đúng: dừng lại trước khi bấm link hoặc gửi thông tin. Bác chỉ cần giữ tin nhắn làm bằng chứng và hỏi người thân nếu còn phân vân."],
        })
    allowed_situations = {"clicked", "sent_money", "shared_code"}
    if not situations or "none" in situations or not set(situations).issubset(allowed_situations):
        return jsonify({"error": "Vui lòng chọn các tình huống hợp lệ."}), 400
    fallback = {
        "clicked": [
            "1. Ngắt thao tác với đường dẫn. Câu nói mẫu: Tôi đã bấm vào link lạ, xin hướng dẫn kiểm tra tài khoản.",
            "2. Đổi mật khẩu tài khoản liên quan nếu đã nhập thông tin. Câu nói mẫu: Tôi cần khóa phiên đăng nhập đáng ngờ.",
            "3. Gọi ngân hàng qua số trong danh sách hỗ trợ nếu liên quan tiền. Câu nói mẫu: Tôi nghi bị lừa qua link, xin kiểm tra giao dịch."
        ],
        "sent_money": [
            "1. Gọi ngay ngân hàng của bác trong danh sách hỗ trợ để yêu cầu tra soát. Câu nói mẫu: Tôi vừa chuyển khoản nghi lừa đảo, xin hỗ trợ phong tỏa/tra soát.",
            "2. Lưu ảnh chụp tin nhắn, số tài khoản, thời gian giao dịch. Câu nói mẫu: Tôi có bằng chứng giao dịch và tin nhắn.",
            "3. Gọi 113 nếu có đe dọa trực tiếp. Câu nói mẫu: Tôi đang bị đe dọa sau khi chuyển tiền."
        ],
        "shared_code": [
            "1. Gọi ngân hàng trong danh sách hỗ trợ để khóa dịch vụ khẩn cấp. Câu nói mẫu: Tôi đã cung cấp mã xác thực, xin khóa giao dịch ngay.",
            "2. Đổi mật khẩu và đăng xuất khỏi thiết bị lạ. Câu nói mẫu: Tôi cần hủy phiên đăng nhập không phải của tôi.",
            "3. Báo cáo tin nhắn/cuộc gọi lừa đảo qua 156 hoặc 5656. Câu nói mẫu: Tôi muốn phản ánh tin nhắn lừa đảo."
        ],
    }
    fallback_steps = []
    for situation in situations:
        for step in fallback[situation]:
            if step not in fallback_steps:
                fallback_steps.append(step)
    fallback_steps = fallback_steps[:5]
    situation_context = ", ".join(situations)
    try:
        data = ask_gemini(rescue_prompt(situation_context, result, HOTLINES))
        steps = clean_rescue_steps(data.get("steps", [])) if isinstance(data, dict) else []
        return jsonify({"source": "gemini", "steps": steps or fallback_steps})
    except Exception:
        return jsonify({"source": "fallback", "steps": fallback_steps})


@app.route("/api/history-view", methods=["POST"])
def history_view():
    try:
        result = restore_result(read_body())
        result["html"] = result_html(result)
        return jsonify(result)
    except Exception:
        return jsonify({"error": "Kết quả cũ không còn đủ dữ liệu để mở lại."}), 400


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5001)), debug=debug)
