import ast
import json
import os
import re
import textwrap
import unicodedata
import uuid
from io import BytesIO
from html import escape, unescape
from xml.sax.saxutils import escape as xml_escape

import requests
from flask import Flask, abort, jsonify, render_template, request, send_file


app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

# ===== Backend Configuration =====
# MAX_PROMPT_CHARS protects the app from sending very large text to Gemini.
# This keeps requests cheaper, faster, and less likely to fail on API limits.
MAX_PROMPT_CHARS = 7000

# shared_results.json is the small file database for permanent history and share links.
# For a school demo this is simpler than adding a full SQL database.
SHARED_RESULTS_FILE = os.path.join(os.path.dirname(__file__), "shared_results.json")

# This message is reused in outputs so users remember the app is educational.
LEGAL_TEXT = "ScamCheck là công cụ giáo dục do nhóm học viên phát triển và không thay thế cảnh báo chính thức từ ngân hàng hoặc cơ quan chức năng."

# Trusted official domains are used for deterministic local link checks.
# Gemini can miss typo domains, so the backend also checks obvious brand lookalikes.
OFFICIAL_DOMAINS = {
    "vietcombank": ["vietcombank.com.vn"],
    "bidv": ["bidv.com.vn"],
    "vietinbank": ["vietinbank.vn"],
    "agribank": ["agribank.com.vn"],
    "techcombank": ["techcombank.com", "techcombank.com.vn"],
    "mbbank": ["mbbank.com.vn"],
    "acb": ["acb.com.vn"],
    "sacombank": ["sacombank.com.vn"],
    "vpbank": ["vpbank.com.vn", "cskh.vpbank.com.vn"],
    "tpbank": ["tpb.vn", "tpbank.com.vn"],
    "momo": ["momo.vn"],
}


@app.after_request
def add_security_headers(response):
    """Add security headers to every HTTP response.

    The microphone permission is limited to this same website, while camera and
    location are disabled. This helps Chrome trust the app more and prevents
    unrelated browser features from being opened accidentally.
    """
    response.headers["Permissions-Policy"] = "microphone=(self), camera=(), geolocation=()"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.before_request
def block_dotfile_paths():
    """Never let SPA fallback make secret-looking dotfiles appear reachable."""
    path_parts = request.path.replace("\\", "/").split("/")
    if any(part.startswith(".") for part in path_parts if part):
        abort(404)
    blocked_names = {"__pycache__", "templates", "app.py", "shared_results.json", "requirements.txt"}
    blocked_suffixes = (".py", ".pyc", ".log", ".sqlite", ".db")
    if any(part in blocked_names for part in path_parts if part):
        abort(404)
    if request.path.lower().endswith(blocked_suffixes):
        abort(404)

# ===== Built-In Demo Data =====
# These lists feed the scam library, sample analyzer buttons, practice mode,
# and official support numbers. Keeping them in Python makes the project easy
# for students to edit without a database migration.
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

HOTLINE_ALIASES = {
    "Vietcombank": ["vietcombank", "vcb", "vietcom", "ngoai thuong"],
    "BIDV": ["bidv", "dau tu phat trien"],
    "VietinBank": ["vietinbank", "vietin", "ctg", "cong thuong"],
    "Agribank": ["agribank", "nong nghiep"],
    "Techcombank": ["techcombank", "tcb", "techcom"],
    "MB Bank": ["mb bank", "mbbank", "mb", "m b bank", "quan doi"],
    "ACB": ["acb", "a c b", "a chau"],
    "Sacombank": ["sacombank", "stb", "sacom"],
    "VPBank": ["vpbank", "vp bank", "v p bank", "vpb", "viet nam thinh vuong"],
    "TPBank": ["tpbank", "tp bank", "tpb", "tien phong"],
}

BANK_CONTACT_DETAILS = {
    "Vietcombank": {
        "official_url": "https://www.vietcombank.com.vn/vi-VN/KHCN/Lien-he-va-Ho-tro/Lien-he-Cham-soc-khach-hang",
        "report_contact": "homthutogiac@vietcombank.com.vn",
        "report_hint": "Gui to giac/gian mao den email cua Vietcombank hoac goi hotline 24/7.",
    },
    "BIDV": {
        "official_url": "https://bidv.com.vn/vn/ca-nhan/lien-he",
        "report_hint": "Goi BIDV Contact Center de khoa the/khoa user ngan hang dien tu khi khan cap.",
    },
    "VietinBank": {
        "official_url": "https://contact.vietinbank.vn/",
        "report_contact": "contact@vietinbank.vn",
        "report_hint": "Lien he cong CSKH VietinBank hoac email chinh thuc neu nghi gia mao.",
    },
    "Agribank": {
        "official_url": "https://www.agribank.com.vn/vn/lien-he",
        "report_contact": "cskh@agribank.com.vn",
        "report_hint": "Lien he Trung tam cham soc, ho tro khach hang Agribank.",
    },
    "Techcombank": {
        "official_url": "https://techcombank.com/en/contact-us",
        "report_contact": "call_center@techcombank.com.vn",
        "report_hint": "Lien he hotline/email chinh thuc cua Techcombank neu nghi ro ri thong tin.",
    },
    "MB Bank": {
        "official_url": "https://www.mbbank.com.vn/",
        "report_hint": "Dung app/website MB Bank chinh thuc de tim kenh ho tro cap nhat.",
    },
    "ACB": {
        "official_url": "https://acb.com.vn/lien-he",
        "report_contact": "acb@acb.com.vn",
        "report_hint": "Lien he ACB Contact Center 247 hoac email chinh thuc neu nghi gia mao.",
    },
    "Sacombank": {
        "official_url": "https://www.sacombank.com.vn/",
        "report_hint": "Dung website/app Sacombank chinh thuc de tim kenh ho tro cap nhat.",
    },
    "VPBank": {
        "official_url": "https://cskh.vpbank.com.vn/contact",
        "report_contact": "chamsockhachhang@vpbank.com.vn",
        "report_hint": "Gui khieu nai/to cao qua cong CSKH VPBank hoac email chinh thuc.",
    },
    "TPBank": {
        "official_url": "https://tpb.vn/wps/portal/vni/faqs/ngan-hang-ca-nhan",
        "report_hint": "Lien he hotline TPBank hoac chi nhanh gan nhat neu nghi gia mao/lua dao.",
    },
}

for row in HOTLINES:
    row.update(BANK_CONTACT_DETAILS.get(row.get("name", ""), {}))

BANK_CASE_TERMS = [
    "bank", "ngan hang", "tai khoan", "the", "otp", "ma otp", "ma xac thuc",
    "chuyen khoan", "nap tien", "rut tien", "giao dich", "so du", "khoa tai khoan",
    "internet banking", "mobile banking", "smart otp", "credit", "debit",
]

URGENT_CASE_TERMS = [
    "da bam", "da nhap", "da gui", "da chuyen", "da tra", "da thanh toan",
    "otp", "mat khau", "cccd", "cmnd", "ma pin", "so the", "cai app",
]

APP_USAGE_TERMS = [
    "cach dung", "dung app", "su dung app", "xai app", "huong dan", "app nay sao",
    "upload", "tai anh", "tai tep", "file", "pdf", "xuat pdf", "mo pdf",
    "lich su", "history", "mo lai", "xoa lich su", "mo link", "trang nay",
    "nut", "chatbox", "hoi ai", "ket qua o dau",
]


def load_env():
    """Load key=value lines from .env into environment variables.

    Flask does not automatically read .env in every deployment environment.
    This helper lets students put API keys in a local .env file without adding
    another package. Blank lines and comment lines are ignored.
    """
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
    # Học sinh có thể dùng 1 key trong GEMINI_API_KEY hoặc nhiều key trong
    # GEMINI_API_KEYS, ngăn cách bằng dấu phẩy, dấu cách hoặc dấu chấm phẩy.
    raw = " ".join([
        os.getenv("GEMINI_API_KEY", ""),
        os.getenv("GEMINI_API_KEYS", ""),
        os.getenv("GOOGLE_API_KEY", ""),
    ])
    # dict.fromkeys giữ nguyên thứ tự nhưng bỏ key trùng để app không thử lặp lại.
    keys = [key.strip() for key in re.split(r"[\s,;]+", raw) if key.strip()]
    return list(dict.fromkeys(keys))


def gemini_models():
    """Return the Gemini model fallback list.

    The app first respects GEMINI_MODELS or GEMINI_MODEL from .env. If those are
    missing or fail, it falls back to common Flash models so one renamed/blocked
    model does not break the whole demo.
    """
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
    """Convert a score-like value into an integer between 0 and 100.

    Gemini might return a number, a numeric string, or something invalid. This
    helper keeps score handling consistent and lets callers provide a fallback.
    """
    try:
        return max(0, min(100, round(float(value))))
    except Exception:
        return fallback


def require_ai_score(data, fallback=None):
    """Read Gemini's risk score from possible field names.

    The prompts ask for riskpercentage, but older saved results or imperfect AI
    responses may use risk_percentage, danger_score_percent, or score. If the
    score is missing and no fallback is passed, the caller gets a clear error.
    """
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
    """Map a numeric risk score to the CSS risk class and Vietnamese label."""
    if score >= 76:
        return "danger", "Nguy hiểm"
    if score >= 26:
        return "suspicious", "Nghi ngờ"
    return "safe", "An toàn"


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
    """Add a safe text-highlight range for risky phrases.

    Very short ranges are noisy, and very long ranges make the whole message
    yellow. This function keeps highlights focused on useful evidence.
    """
    if end <= start or end - start < 3:
        return
    # Do not highlight the whole prompt; the yellow should point to specific risk cues.
    if end - start > 120 or end - start > text_length * 0.45:
        return
    spans.append((start, end))


def highlight_original(text, evidence):
    """Return HTML for the original message with risky fragments marked.

    It combines deterministic regex cues, such as OTP/link/urgent wording, with
    quotes returned by Gemini. All user text is escaped before becoming HTML.
    """
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
    """Estimate how many sentences are in a short explanation."""
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




def restore_result(data):
    """Convert older or incomplete saved results into the current format.

    Permanent history can contain data saved by older versions of the app. This
    normalizer fills missing fields so the frontend can still render them safely.
    """
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
        "summary": clean_ai_text(data.get("summary")) or "Kết quả kiểm tra đã lưu",
        "explanation": clean_ai_text(data.get("explanation")) or "Mở lại kết quả đã phân tích trên thiết bị này.",
        "uncertainty": clean_ai_text(data.get("uncertainty")) or "Hãy xác minh qua nguồn chính thức nếu còn lo lắng.",
        "evidence": clean_ai_rows(data.get("evidence")) if isinstance(data.get("evidence"), list) else [],
        "next_actions": clean_actions(actions if isinstance(actions, list) else []),
        "rescue_options": clean_rescue_options(
            data.get("rescue_options") or data.get("rescueOptions") or data.get("situation_options")
        ),
        "checked_text": data.get("checked_text") or data.get("inputText", ""),
    }


def read_body():
    """Read JSON request data and always return a dictionary.

    Flask returns None when a request has no JSON body or invalid JSON. Returning
    {} keeps route functions simpler and prevents many NoneType errors.
    """
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def load_shared_results():
    """Read the permanent result store used by history and share links."""
    if not os.path.exists(SHARED_RESULTS_FILE):
        return {}
    try:
        with open(SHARED_RESULTS_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_shared_results(data):
    """Write the permanent result store back to disk as readable UTF-8 JSON."""
    with open(SHARED_RESULTS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def share_result_payload(data):
    """Normalize, render, and store one shareable analysis result."""
    result = restore_result(data)
    share_id = str(result.get("share_id") or result.get("id") or uuid.uuid4().hex[:12])
    result["share_id"] = re.sub(r"[^a-zA-Z0-9_-]", "", share_id)[:40] or uuid.uuid4().hex[:12]
    result["id"] = result.get("id") or result["share_id"]
    result["html"] = result_html(result)

    shared = load_shared_results()
    shared[result["share_id"]] = result
    save_shared_results(shared)
    return result


def shared_history_items():
    """Return saved results sorted newest first for the History screen."""
    items = []
    for share_id, result in load_shared_results().items():
        if not isinstance(result, dict):
            continue
        restored = restore_result(result)
        restored["share_id"] = restored.get("share_id") or share_id
        restored["id"] = restored.get("id") or restored["share_id"]
        restored["share_url"] = f"/analysis/{restored['share_id']}"
        items.append(restored)
    return sorted(items, key=lambda item: item.get("time") or "", reverse=True)


def result_pdf_sections(result):
    """Convert a result dictionary into titled PDF sections.

    The PDF generator expects a predictable list of sections. This function
    prepares evidence rows, action rows, original text, psychology notes, and the
    educational disclaimer in one place.
    """
    evidence_rows = []
    for item in result.get("evidence", []):
        if isinstance(item, dict):
            evidence_rows.append({
                "quote": pdf_safe_text(item.get("quote") or "Dấu hiệu", 220),
                "why": pdf_safe_text(item.get("why") or item.get("explanation") or "", 700),
            })

    action_rows = []
    for item in result.get("next_actions", []):
        if isinstance(item, dict):
            action_rows.append({
                "label": pdf_safe_text(item.get("label") or "Việc cần làm", 160),
                "detail": pdf_safe_text(item.get("detail") or item.get("prompt") or "", 700),
            })

    sections = [
        ("Phân tích kỹ thuật", [pdf_safe_text(result.get("summary", ""), 700), pdf_safe_text(result.get("explanation", ""), 1200)]),
        ("Dấu hiệu phát hiện", evidence_rows or [{"quote": "Chưa có dấu hiệu riêng", "why": "Gemini chưa tách được dấu hiệu cụ thể từ nội dung này."}]),
        ("Nên làm gì tiếp?", action_rows or [{"label": "Kiểm tra lại qua kênh chính thức", "detail": "Không vội làm theo tin nhắn nếu còn nghi ngờ."}]),
        ("Tin gốc đã kiểm tra", [pdf_safe_text(result.get("checked_text", "") or result.get("inputText", ""), 2400)]),
    ]

    if result.get("psychology"):
        sections.append(("Cô tâm lý nhắc nhẹ", [pdf_safe_text(result.get("psychology", ""), 900)]))

    sections.append((
        "Ghi chú giáo dục",
        ["ScamCheck là công cụ giáo dục do học sinh phát triển. Kết quả chỉ mang tính tham khảo và không thay thế cảnh báo chính thức từ ngân hàng hoặc cơ quan chức năng."]
    ))
    return sections


def vietnamese_font_path():
    """Pick a local Unicode font so Vietnamese accents render correctly in PDFs."""
    candidates = [
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "arial.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    return next((path for path in candidates if os.path.exists(path)), None)


def build_result_pdf(result):
    """Create a polished multi-page PDF that mirrors the web result card.

    ReportLab builds the file in memory with BytesIO, so the app can return it
    directly to the browser without creating temporary PDF files on disk.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    class ScoreCircle(Flowable):
        """Draw the percentage badge shown at the top of the PDF."""
        def __init__(self, score, color, font):
            """Store drawing settings for one circular score badge."""
            super().__init__()
            self.score = score
            self.color = color
            self.font = font
            self.width = 34 * mm
            self.height = 34 * mm

        def draw(self):
            """Draw the ring, percentage text, and small rủi ro label."""
            canvas = self.canv
            radius = 16 * mm
            center = self.width / 2
            canvas.setStrokeColor(colors.HexColor("#f2e7e1"))
            canvas.setLineWidth(7)
            canvas.circle(center, center, radius, stroke=1, fill=0)
            canvas.setStrokeColor(self.color)
            canvas.setLineWidth(7)
            canvas.arc(center - radius, center - radius, center + radius, center + radius, 90, -360 * self.score / 100)
            canvas.setFillColor(colors.white)
            canvas.circle(center, center, radius - 4, stroke=0, fill=1)
            canvas.setFillColor(colors.HexColor("#172033"))
            canvas.setFont(self.font, 18)
            canvas.drawCentredString(center, center + 2, f"{self.score}%")
            canvas.setFillColor(colors.HexColor("#667085"))
            canvas.setFont(self.font, 8)
            canvas.drawCentredString(center, center - 11, "rủi ro")

    def paragraph(text, style):
        """Create a ReportLab paragraph while preserving Vietnamese/newlines safely."""
        safe_text = xml_escape(pdf_safe_text(text, 1800)).replace("\n", "<br/>")
        return Paragraph(safe_text, style)

    def text_box(title, body, background="#ffffff", border="#eee2dc"):
        """Create one bordered PDF section for text, evidence, or action rows."""
        rows = [[paragraph(title, styles["BoxTitle"])]]
        if isinstance(body, list) and body and isinstance(body[0], dict):
            for row in body:
                heading = row.get("quote") or row.get("label") or "Nội dung"
                detail = row.get("why") or row.get("detail") or ""
                rows.append([paragraph(f"{heading}\n{detail}", styles["Body"])])
        else:
            for item in body if isinstance(body, list) else [body]:
                rows.append([paragraph(item, styles["Body"])])

        table = Table(rows, colWidths=[170 * mm], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(background)),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(border)),
            ("INNERGRID", (0, 1), (-1, -1), 0.45, colors.HexColor("#f4dfd7")),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        return table

    buffer = BytesIO()
    score = int(result.get("danger_score_percent", 0))
    risk_color = colors.HexColor("#16a34a" if score < 26 else "#f59e0b" if score < 76 else "#ef4444")
    font_name = "Helvetica"
    font_path = vietnamese_font_path()

    if font_path:
        pdfmetrics.registerFont(TTFont("ScamCheckVietnamese", font_path))
        font_name = "ScamCheckVietnamese"

    base = getSampleStyleSheet()
    styles = {
        "Title": ParagraphStyle("Title", parent=base["Title"], fontName=font_name, fontSize=20, leading=25, textColor=colors.HexColor("#172033"), spaceAfter=8),
        "Body": ParagraphStyle("Body", parent=base["BodyText"], fontName=font_name, fontSize=10.5, leading=16, textColor=colors.HexColor("#536176")),
        "Muted": ParagraphStyle("Muted", parent=base["BodyText"], fontName=font_name, fontSize=9.5, leading=14, textColor=colors.HexColor("#667085")),
        "Pill": ParagraphStyle("Pill", parent=base["BodyText"], fontName=font_name, fontSize=10, leading=14, textColor=colors.white, alignment=TA_CENTER),
        "BoxTitle": ParagraphStyle("BoxTitle", parent=base["Heading3"], fontName=font_name, fontSize=13, leading=17, textColor=colors.HexColor("#172033"), spaceAfter=4),
    }

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="ScamCheck - Kết quả phân tích",
    )

    verdict = result.get("verdict_label", "Kết quả")
    story = []
    pill = Table([[paragraph(f"{verdict} · {score}% rủi ro", styles["Pill"])]], colWidths=[54 * mm])
    pill.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), risk_color),
        ("BOX", (0, 0), (-1, -1), 0, risk_color),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(pill)
    story.append(Spacer(1, 5 * mm))
    story.append(paragraph("Phân tích kỹ thuật", styles["Title"]))
    story.append(paragraph(result.get("summary", ""), styles["Muted"]))
    story.append(Spacer(1, 5 * mm))

    score_table = Table([
        [
            ScoreCircle(score, risk_color, font_name),
            [
                paragraph(result.get("zone_title", verdict), styles["Title"]),
                paragraph(result.get("uncertainty", ""), styles["Muted"]),
            ],
        ]
    ], colWidths=[42 * mm, 124 * mm])
    score_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffaf7")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#f1ddd5")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 6 * mm))

    for title, body in result_pdf_sections(result):
        story.append(text_box(title, body, "#fff8f4" if title in {"Dấu hiệu phát hiện", "Tin gốc đã kiểm tra"} else "#ffffff"))
        story.append(Spacer(1, 5 * mm))

    doc.build(story)
    buffer.seek(0)
    return buffer


def build_fallback_result_pdf(result):
    """Create a simpler PDF when the polished ReportLab layout cannot fit."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    buffer = BytesIO()
    page_width, page_height = A4
    font_name = "Helvetica"
    font_path = vietnamese_font_path()

    if font_path:
        pdfmetrics.registerFont(TTFont("ScamCheckVietnameseFallback", font_path))
        font_name = "ScamCheckVietnameseFallback"

    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle("ScamCheck - Kết quả phân tích")
    margin = 42
    y = page_height - margin
    line_height = 15

    def new_page():
        nonlocal y
        pdf.showPage()
        y = page_height - margin

    def draw_line(text, size=10.5, bold=False):
        nonlocal y
        if y < margin + line_height:
            new_page()
        pdf.setFont(font_name, size)
        pdf.drawString(margin, y, pdf_safe_text(text, 900))
        y -= line_height + (2 if bold else 0)

    def draw_wrapped(text, size=10.5):
        width = 92
        for paragraph_text in pdf_safe_text(text, 2200).splitlines() or [""]:
            lines = textwrap.wrap(paragraph_text, width=width, break_long_words=True, replace_whitespace=False) or [""]
            for line in lines:
                draw_line(line, size=size)

    score = int(result.get("danger_score_percent", 0))
    draw_line("ScamCheck - Kết quả phân tích", 17, True)
    draw_line(f"{pdf_safe_text(result.get('verdict_label') or 'Kết quả', 80)} - {score}% rủi ro", 12, True)
    y -= 8

    for title, body in result_pdf_sections(result):
        draw_line(title, 13, True)
        if isinstance(body, list) and body and isinstance(body[0], dict):
            for row in body:
                heading = row.get("quote") or row.get("label") or "Nội dung"
                detail = row.get("why") or row.get("detail") or ""
                draw_wrapped(f"{heading}\n{detail}")
                y -= 5
        else:
            for item in body if isinstance(body, list) else [body]:
                draw_wrapped(item)
        y -= 10

    pdf.save()
    buffer.seek(0)
    return buffer


def character_count(text):
    """Count characters after converting missing values to an empty string."""
    return len(str(text or ""))


def too_long_error():
    """Return the standard JSON error for over-long Gemini prompts."""
    return jsonify({"error": f"Nội dung quá dài. Vui lòng rút gọn dưới {MAX_PROMPT_CHARS} ký tự rồi thử lại."}), 400


def prompt_is_too_long(*parts):
    """Check all prompt pieces together against MAX_PROMPT_CHARS."""
    text = " ".join(str(part or "") for part in parts)
    return character_count(text) > MAX_PROMPT_CHARS


def extract_links(text):
    """Extract likely URLs/domains from user text for local safety checks."""
    pattern = r"(?i)\b(?:https?://|www\.)[^\s<>()]+|\b[a-z0-9-]+\.[a-z]{2,}(?:/[^\s<>()]*)?"
    return [link.rstrip(".,;:!?)]}") for link in re.findall(pattern, str(text or ""))]


def domain_of(link):
    """Normalize a URL into only its lowercase domain name."""
    link = link.lower()
    link = re.sub(r"^https?://", "", link)
    link = re.sub(r"^www\.", "", link)
    return link.split("/", 1)[0]


def edit_distance_at_most(left, right, limit=2):
    """Return True when two short strings are within a small edit distance."""
    left = str(left or "")
    right = str(right or "")
    if abs(len(left) - len(right)) > limit:
        return False
    previous = list(range(len(right) + 1))
    for index, left_char in enumerate(left, start=1):
        current = [index]
        row_min = current[0]
        for jndex, right_char in enumerate(right, start=1):
            insert = current[jndex - 1] + 1
            delete = previous[jndex] + 1
            replace = previous[jndex - 1] + (left_char != right_char)
            value = min(insert, delete, replace)
            current.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return False
        previous = current
    return previous[-1] <= limit


def suspicious_brand_labels(domain, brand):
    """Yield domain pieces that are typo-close to a known brand."""
    compact_domain = re.sub(r"[^a-z0-9]", "", domain.lower())
    labels = re.split(r"[.-]+", domain.lower())
    candidates = {compact_domain, *labels}
    for label in labels:
        candidates.update(token for token in re.split(r"[-_]+", label) if token)

    for candidate in candidates:
        candidate = re.sub(r"[^a-z0-9]", "", candidate)
        if len(candidate) < max(3, len(brand) - 2):
            continue
        if brand in candidate:
            yield candidate
            continue
        if len(brand) < 6:
            continue
        prefix_len = 3 if len(brand) >= 8 else 2
        if len(candidate) >= len(brand):
            for start in range(0, len(candidate) - len(brand) + 1):
                piece = candidate[start:start + len(brand)]
                if piece[:prefix_len] == brand[:prefix_len] and edit_distance_at_most(piece, brand, 1):
                    yield piece
        elif candidate[:prefix_len] == brand[:prefix_len] and edit_distance_at_most(candidate, brand, 2):
            yield candidate




def looks_like_fake_domain(domain):
    """Return warnings when a domain impersonates or typo-squats a known brand."""
    domain = domain.lower()
    compact = re.sub(r"[^a-z0-9]", "", domain)
    confusable_compact = compact.replace("rn", "m").replace("0", "o").replace("1", "l")
    warnings = []
    for brand, official in OFFICIAL_DOMAINS.items():
        if any(domain == real or domain.endswith("." + real) or domain.endswith(real) for real in official):
            continue
        if brand in compact or brand in confusable_compact:
            warnings.append(f"Tên miền {domain} có thể giả mạo {brand}: có tên thương hiệu trong một miền không chính thức.")
            continue
        if list(suspicious_brand_labels(domain, brand)):
            warnings.append(f"Tên miền {domain} gần giống {brand} nhưng không phải miền chính thức; có thể là tên miền giả mạo hoặc sai chính tả.")

    shorteners = ("bit.ly", "tinyurl.com", "cutt.ly", "bom.so", "goo.gl", "t.co")
    if domain in shorteners:
        warnings.append(f"Đường dẫn {domain} là link rút gọn, cần kiểm tra trước khi bấm.")
    return warnings


def link_warnings(text):
    """Build evidence rows for suspicious links before Gemini is involved."""
    links = extract_links(text)
    rows = []
    for link in links:
        domain = domain_of(link)
        for warning in looks_like_fake_domain(domain):
            rows.append({"quote": link, "why": warning})
    return rows


def is_quota_error(text):
    """Detect Gemini quota/rate-limit messages that should trigger key rotation."""
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
    """Detect invalid or unauthorized Gemini API key errors."""
    text = str(text).lower()
    return (
        "api key not valid" in text
        or "unauthenticated" in text
        or "permission_denied" in text
        or "api_key_invalid" in text
    )


def is_model_error(text):
    """Detect errors caused by a model name that Gemini cannot use."""
    text = str(text).lower()
    return "is not found for api version" in text or "not_supported" in text or "model not found" in text


def is_temporary_error(text):
    """Detect retryable network/server errors from Gemini."""
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
    """Convert technical Gemini exceptions into user-friendly Vietnamese text."""
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
    """Parse JSON even when Gemini wraps it in markdown fences or extra text."""
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


def clean_ai_text(text, limit=None):
    """Remove model formatting artifacts before text reaches UI or PDF."""
    text = unescape(str(text or "")).strip()
    text = text.replace("`n", "\n").replace("\\n", "\n")
    text = re.sub(r"^```(?:json|html|javascript|js|python|text)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(?:p|div|li|h[1-6])\s*>", "\n", text, flags=re.I)
    text = re.sub(r"</?[^>]+>", "", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    text = re.sub(r"^\s*(?:answer|summary|explanation|uncertainty|why|prompt)\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if limit:
        text = text[:limit].strip()
    return text


def clean_ai_rows(value, limit=None):
    """Clean each string value inside a small AI-produced object/list."""
    if isinstance(value, dict):
        return {key: clean_ai_rows(row, limit) for key, row in value.items()}
    if isinstance(value, list):
        return [clean_ai_rows(row, limit) for row in value]
    if isinstance(value, str):
        return clean_ai_text(value, limit)
    return value


def pdf_safe_text(text, limit=1400):
    """Return plain bounded text that ReportLab can render reliably."""
    text = clean_ai_text(text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"(\S{56})(?=\S)", r"\1 ", text)
    text = text.strip()
    if limit and len(text) > limit:
        text = text[:limit].rstrip() + "..."
    return text


def ask_gemini(prompt, image=None):
    """Call Gemini and rotate through available keys/models after errors.

    This is the main AI gateway for the backend. Every feature that needs Gemini
    sends a prompt here. The nested loops try model 1/key 1, model 1/key 2, and
    so on, so one exhausted key does not stop the app.
    """
    keys = gemini_keys()
    if not keys:
        raise RuntimeError("Chưa có Gemini API key trong .env")

    # parts là nội dung gửi cho AI: luôn có văn bản, có thể kèm thêm ảnh.
    parts = [{"text": prompt}]
    if image and image.get("dataUrl") and image.get("mimeType"):
        image_data = image["dataUrl"].split(",", 1)[1]
        parts.append({"inline_data": {"mime_type": image["mimeType"], "data": image_data}})

    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.15},
    }

    last_error = "Gemini chưa phản hồi."
    tried = []
    for model in gemini_models():
        # Với mỗi model, thử từng key theo thứ tự. Nếu một key hết quota hoặc lỗi tạm
        # thời, vòng lặp tiếp tục sang key tiếp theo để app vẫn có cơ hội hoạt động.
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
                    # Model không tồn tại hoặc không hỗ trợ thì đổi model, không thử tiếp cùng model đó.
                    break
                if is_quota_error(last_error) or is_key_error(last_error) or is_temporary_error(last_error):
                    # Key hết token/quota, sai quyền hoặc server bận: chuyển sang key kế tiếp.
                    continue
            except Exception as error:
                last_error = str(error)
                tried.append(f"key {key_index}, {model}: {type(error).__name__}")
                continue
    raise RuntimeError(last_error + "\nTried: " + "; ".join(tried[-8:]))


















def clean_result(data, message):
    """Normalize Gemini JSON into the exact shape expected by the frontend.

    Gemini responses can be incomplete or slightly inconsistent. This function
    adds deterministic link warnings, clamps the score, cleans evidence/actions,
    and returns the stable object that JavaScript expects.
    """
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
            quote = clean_ai_text(row.get("quote", ""), 180)
            why = clean_ai_text(row.get("why") or row.get("explanation") or "")
            if quote or why:
                cleaned_evidence.append({"quote": quote[:180], "why": detailed_evidence_why(quote, why)[:820]})
    return {
        "source": "gemini",
        "risk": risk,
        "danger_score_percent": score,
        "verdict_label": data.get("verdict_label") or default_label,
        "zone_title": data.get("zone_title") or data.get("zoneTitle") or default_label,
        "summary": clean_ai_text(data.get("summary")) or "Kết quả cần được kiểm tra thêm.",
        "explanation": clean_ai_text(data.get("explanation")) or "AI chưa trả đủ cấu trúc, nên ScamCheck hiển thị mức nghi ngờ mặc định để ứng dụng không bị gãy.",
        "uncertainty": clean_ai_text(data.get("uncertainty")) or "Hãy xác minh qua nguồn chính thức nếu còn lo lắng.",
        "evidence": cleaned_evidence,
        "next_actions": clean_actions(actions, exact_three=True),
        "rescue_options": clean_rescue_options(
            data.get("rescue_options") or data.get("rescueOptions") or data.get("situation_options")
        ),
        "checked_text": message,
    }


def add_psychology_if_needed(result, message, image=None):
    """Ask Gemini for a short empathy-focused explanation only when needed."""
    if result["risk"] == "safe":
        return result
    try:
        data = ask_gemini(psychology_prompt(message, result), image)
        answer = clean_ai_text(data.get("answer", "")) if isinstance(data, dict) else ""
        result["psychology"] = answer or "Cô thấy tin này dùng cảm giác gấp gáp để bác hành động nhanh. Điều đó không có nghĩa là bác đã làm sai hay phải hoảng lên. Kẻ lừa đảo thường cố làm mình sợ mất tiền, mất tài khoản hoặc bỏ lỡ cơ hội. Bác cứ dừng lại vài phút, thở chậm và nhìn từng yêu cầu trong tin. Nếu có link, tiền, OTP hoặc giấy tờ cá nhân thì mình chỉ kiểm tra qua kênh chính thức. Bác có thể nhờ người thân xem cùng trước khi làm bất kỳ bước nào."
    except Exception:
        result["psychology_error"] = "Cô tâm lý đang bận, bác thử lại sau. Phần phân tích kỹ thuật vẫn hiển thị đầy đủ ở trên."
    return result


def clean_actions(actions, exact_three=False):
    """Keep Gemini-provided action buttons short and frontend-safe."""
    cleaned = []
    for index, action in enumerate(actions[:4]):
        if isinstance(action, dict):
            label = clean_ai_text(action.get("label", ""), 80)
            prompt = clean_ai_text(action.get("prompt", ""), 240)
        else:
            label = clean_ai_text(action, 80)
            prompt = label
        if label:
            cleaned.append({"id": f"step_{index + 1}", "label": label[:80], "prompt": prompt[:240]})
    if cleaned:
        return cleaned[:3] if exact_three else cleaned
    return []


def clean_rescue_options(options):
    """Clean Gemini-generated rescue choices for the result checklist.

    Each option needs a stable id, a label, and a detail sentence. The frontend
    uses those ids when the user chooses what they already did.
    """
    cleaned = []
    seen = set()
    for index, option in enumerate(options if isinstance(options, list) else []):
        if isinstance(option, dict):
            raw_id = str(option.get("id", "")).strip().lower()
            label = clean_ai_text(option.get("label", ""), 90)
            detail = clean_ai_text(option.get("detail") or option.get("prompt") or "", 220)
        else:
            raw_id = ""
            label = clean_ai_text(option, 90)
            detail = ""
        if not label:
            continue
        option_id = re.sub(r"[^a-z0-9_]+", "_", raw_id).strip("_") or f"ai_option_{index + 1}"
        option_id = option_id[:42]
        if option_id in seen:
            option_id = f"{option_id}_{index + 1}"[:48]
        seen.add(option_id)
        cleaned.append({
            "id": option_id,
            "label": label[:90],
            "detail": detail[:220],
        })
    return cleaned[:5]


def compact_result(item):
    """Keep useful AI context while excluding saved HTML and large browser data."""
    if not isinstance(item, dict):
        return {}
    fields = ("time", "inputText", "checked_text", "risk", "danger_score_percent",
              "verdict_label", "zone_title", "summary", "explanation", "uncertainty",
              "evidence", "next_actions", "rescue_options")
    return {name: item.get(name) for name in fields if item.get(name) not in (None, "", [])}




def rescue_prompt(selected_options, result, hotlines):
    """Build the urgent-action prompt for rescue mode.

    Rescue mode is narrower than normal chat: it should output concrete steps
    based on what the user says they already did, and it can only use approved
    phone numbers from HOTLINES.
    """
    context = {
        "cac_lua_chon_nguoi_dung_da_chon": selected_options,
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
    """Return the whitelist of support numbers the AI is allowed to mention."""
    return {row["phone"] for row in HOTLINES}


def clean_rescue_steps(raw_steps):
    """Drop rescue advice that invents phone numbers outside the trusted list."""
    phones = allowed_phone_set()
    cleaned = []
    for step in raw_steps if isinstance(raw_steps, list) else []:
        text = clean_ai_text(step, 420)
        found = set(re.findall(r"\b\d{3,11}\b", text))
        if found and not found.issubset(phones):
            continue
        if text:
            cleaned.append(text[:420])
    return cleaned[:5]




def sanitize_unapproved_phones(text):
    """Mask phone numbers that are not in the curated HOTLINES list."""
    allowed = allowed_phone_set()
    source = str(text or "")

    def replace(match):
        """Keep trusted phone numbers and mask any phone number Gemini invented."""
        phone = match.group(0)
        if match.end() < len(source) and source[match.end()] == "%":
            return phone
        return phone if phone in allowed else "[số chưa xác minh]"

    return re.sub(r"\b\d{3,11}\b", replace, source)


def contains_allowed_phone(*texts):
    """Detect whether Gemini already gave at least one approved support number."""
    allowed = allowed_phone_set()
    found = set()
    for text in texts:
        found.update(re.findall(r"\b\d{3,11}\b", str(text or "")))
    return bool(found & allowed)


def normalize_contact_text(text):
    """Lowercase text and remove accents for bank/contact matching."""
    normalized = unicodedata.normalize("NFD", str(text or "").lower())
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", normalized).strip()


def hotline_context_blob(result, question="", answer_text="", ai_steps=None):
    """Collect the active case text used for contact matching."""
    if not isinstance(result, dict):
        result = {}
    evidence = result.get("evidence") if isinstance(result.get("evidence"), list) else []
    evidence_text = " ".join(
        " ".join(str(row.get(key, "")) for key in ("quote", "why", "explanation"))
        for row in evidence if isinstance(row, dict)
    )
    actions = result.get("next_actions") if isinstance(result.get("next_actions"), list) else []
    action_text = " ".join(
        " ".join(str(row.get(key, "")) for key in ("label", "prompt", "detail"))
        for row in actions if isinstance(row, dict)
    )
    return normalize_contact_text(" ".join([
        question,
        answer_text,
        " ".join(ai_steps or []),
        str(result.get("summary", "")),
        str(result.get("explanation", "")),
        str(result.get("uncertainty", "")),
        str(result.get("checked_text", "")),
        evidence_text,
        action_text,
    ]))


def case_has_bank_context(blob):
    """Return True when the case appears related to banking, cards, money or OTP."""
    return any(term in blob for term in BANK_CASE_TERMS)


def case_has_urgent_private_info(blob):
    """Return True when the user may already have exposed money or private data."""
    return any(term in blob for term in URGENT_CASE_TERMS)


def is_app_usage_question(question):
    """Detect normal app-help questions so chat does not force scam advice."""
    blob = normalize_contact_text(question)
    return any(term in blob for term in APP_USAGE_TERMS)


def matched_hotlines_for_case(result, question="", answer_text="", ai_steps=None, limit=4):
    """Return whitelisted contacts that match this exact scam case."""
    if not isinstance(result, dict):
        return []
    blob = hotline_context_blob(result, question, answer_text, ai_steps)
    if not blob:
        return []

    matches = []
    for row in HOTLINES:
        aliases = [row.get("name", ""), *HOTLINE_ALIASES.get(row.get("name", ""), [])]
        normalized_aliases = [normalize_contact_text(alias) for alias in aliases if alias]
        alias_hit = any(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", blob) for alias in normalized_aliases)
        domain_hit = False
        if not alias_hit and row.get("type") == "bank":
            for domain in {domain_of(link) for link in extract_links(blob)}:
                if any(list(suspicious_brand_labels(domain, alias)) for alias in normalized_aliases if len(alias) >= 3):
                    domain_hit = True
                    break
        if alias_hit or domain_hit:
            matches.append({
                "type": row.get("type", ""),
                "name": row.get("name", ""),
                "phone": row.get("phone", ""),
                "note": row.get("note", ""),
                "official_url": row.get("official_url", ""),
                "report_contact": row.get("report_contact", ""),
                "report_hint": row.get("report_hint", ""),
                "reason": "matched mentioned organization",
            })

    seen = set()
    unique = []
    for row in matches:
        key = row.get("phone")
        if key and key not in seen:
            seen.add(key)
            unique.append(row)

    if unique:
        return unique[:limit]

    return []


def support_contact_context(result, question="", answer_text="", ai_steps=None):
    """Compact support context injected into Gemini chat prompts."""
    blob = hotline_context_blob(result, question, answer_text, ai_steps)
    return {
        "matched_contacts": matched_hotlines_for_case(result, question, answer_text, ai_steps),
        "is_bank_related": case_has_bank_context(blob),
        "urgent_private_info_or_payment": case_has_urgent_private_info(blob),
        "normal_app_usage_question": is_app_usage_question(question),
        "contact_rule": "Only use these matched contacts. If none match, tell bac to verify through the official app/card/website and do not invent numbers.",
    }


def relevant_hotline_support_steps(result, question="", answer_text="", ai_steps=None):
    """Add concrete support contacts when a risky chat answer omits them.

    Gemini sometimes gives good advice but forgets the actual support number. This
    fallback only adds contacts that match the user's current context.
    """
    if not isinstance(result, dict) or result.get("risk") == "safe":
        return []
    context = " ".join([
        question,
        answer_text,
        " ".join(ai_steps or []),
        str(result.get("summary", "")),
        str(result.get("explanation", "")),
        str(result.get("checked_text", "")),
    ]).lower()
    if not re.search(r"tiền|tien|ngân hàng|ngan hang|chuyển khoản|chuyen khoan|otp|thẻ|the|tài khoản|tai khoan|bị đe dọa|bi de doa|đe dọa|de doa|cuộc gọi|cuoc goi|tin nhắn|tin nhan", context):
        return []
    steps = []
    bank_examples = ", ".join(
        f"{row['name']} {row['phone']}" for row in [row for row in HOTLINES if row["type"] == "bank"][:4]
    )
    if re.search(r"tiền|tien|ngân hàng|ngan hang|chuyển khoản|chuyen khoan|otp|thẻ|the|tài khoản|tai khoan", context):
        steps.append(f"Nếu vụ việc liên quan tiền, OTP, thẻ hoặc tài khoản ngân hàng, bác tự mở app/thẻ để gọi số chính thức; ví dụ danh sách ScamCheck có {bank_examples}.")
    if re.search(r"bị đe dọa|bi de doa|đe dọa|de doa|khẩn cấp|khan cap|công an|cong an", context):
        steps.append("Nếu bác đang bị đe dọa trực tiếp hoặc cần hỗ trợ khẩn cấp, gọi Công an 113.")
    if re.search(r"cuộc gọi|cuoc goi|tin nhắn|tin nhan|sms|rác|rac", context):
        steps.append("Nếu muốn phản ánh cuộc gọi hoặc tin nhắn lừa đảo, bác có thể dùng 156 hoặc 5656.")
    return steps[:3]


def needs_followup(result):
    """Gate delayed follow-ups to detective verdicts that need support."""
    return isinstance(result, dict) and result.get("risk") in {"suspicious", "danger"}








def latest_chat_result(data):
    """Find the best current scam analysis for chatbot context."""
    result = data.get("result") if isinstance(data.get("result"), dict) else {}
    if compact_result(result):
        return result

    history = data.get("history", [])
    if isinstance(history, list):
        for row in history:
            if isinstance(row, dict) and compact_result(row):
                return row

    saved = shared_history_items()
    return saved[0] if saved else {}


def chat_data_with_latest_case(data):
    """Ensure chat prompts receive a latest analysis even if browser state is thin."""
    enriched = dict(data) if isinstance(data, dict) else {}
    result = latest_chat_result(enriched)
    if result:
        enriched["result"] = result
        history = enriched.get("history")
        if not isinstance(history, list):
            enriched["history"] = [result]
        elif result not in history:
            enriched["history"] = [result, *history]
    return enriched






def psychology_prompt(message, detective):
    """Build the active short delayed Cô tâm lý prompt used only for 40%+ results."""
    context = {
        "tin_goc": message,
        "ket_qua_tham_tu": compact_result(detective),
    }
    return f"""
Bạn là Cô tâm lý ScamCheck. Xưng là "cô" và gọi người dùng là "bác".
Chỉ trả JSON hợp lệ, không markdown.
Viết ấm áp, không đổ lỗi, không làm bác sợ hơn.
answer chỉ gồm 2 đến 3 câu ngắn bằng tiếng Việt có dấu.
Nhắc đúng 1 chiến thuật tâm lý trong tin và 1 cách bình tĩnh kiểm tra tiếp.

Bối cảnh:
{json.dumps(context, ensure_ascii=False)}

Trả về JSON object:
- answer: 2 đến 3 câu ngắn.
"""


def result_html(item):
    """Render the final active analysis card.

    There are older result_html definitions above from previous iterations. In
    Python, the last function with the same name wins, so this is the one routes
    actually call at runtime.
    """
    score = item["danger_score_percent"]
    risk = item["risk"]
    color = {"safe": "#22c55e", "suspicious": "#f59e0b", "danger": "#ef4444"}.get(risk, "#f59e0b")
    evidence = item.get("evidence", [])
    actions = item.get("next_actions", [])
    original_html = highlight_original(item.get("checked_text", ""), evidence)
    psychology = item.get("psychology")
    psychology_error = item.get("psychology_error")

    def support_text(text):
        """Shorten the active psychology note for the final result card."""
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return " ".join(sentence for sentence in sentences[:3] if sentence).strip()

    psychology_html = ""
    if needs_followup(item) and psychology:
        psychology_html = f"""
        <section class="support-card" aria-label="Cô tâm lý nhắc nhẹ">
          <div class="support-icon" aria-hidden="true">♡</div>
          <div>
            <h3>Cô tâm lý nhắc nhẹ</h3>
            <p>{escape(support_text(psychology))}</p>
          </div>
        </section>"""
    elif needs_followup(item) and psychology_error:
        psychology_html = """
        <p class="support-note">Cô tâm lý đang bận, bác có thể tiếp tục theo các bước bên trên.</p>"""

    evidence_html = "".join(
        f"<div><strong>{escape(str(row.get('quote', 'Dấu hiệu')))}</strong><p>{escape(str(row.get('why') or row.get('explanation') or ''))}</p></div>"
        for row in evidence[:4] if isinstance(row, dict)
    ) or f"<p>{escape(str(item.get('checked_text', '')))}</p>"

    actions_html = "".join(
        f"<button class='action-btn' data-action='{index}'><span>{escape(action['label'])}</span><span>→</span></button>"
        for index, action in enumerate(actions)
    ) or "<p class='hint'>Gemini chưa trả bước tiếp theo phù hợp cho kết quả này.</p>"

    return f"""
<div id="resultCard" style="--risk-color:{color};padding:18px" data-score="{score}">
  <section class="result-head"><span class="pill {risk}" id="scorePill">{escape(item['verdict_label'])} · {score}% rủi ro</span><h2>Phân tích kỹ thuật</h2><p class="hint">{escape(item['summary'])}</p><p>{escape(item['explanation'])}</p></section>
  <div class="result-main"><div id="scoreRing" class="ring" style="--score:{score}%"><strong id="scoreText">{score}%</strong><small>rủi ro</small></div><div><h2 id="zoneTitle">{escape(item['zone_title'])}</h2><p class="hint">{escape(item['uncertainty'])}</p></div></div>
  <div class="grid"><div class="box"><h3>Dấu hiệu phát hiện</h3><div class="evidence">{evidence_html}</div></div><div class="box"><h3>Nên làm gì tiếp?</h3><div class="checks">{actions_html}</div></div></div>
  <div class="box original-text"><h3>Tin gốc đã tô vàng</h3><p>{original_html or "Không có văn bản gốc để tô vàng."}</p></div>
  {psychology_html}
</div>"""


def clean_chat_steps(raw_steps):
    """Final chat next-step cleaner used by /api/chat."""
    phones = allowed_phone_set()
    cleaned = []

    def step_to_text(step):
        if isinstance(step, dict):
            label = clean_ai_text(step.get("label", ""), 80)
            prompt = clean_ai_text(step.get("prompt") or step.get("detail") or step.get("text") or "", 220)
            return f"{label}: {prompt}".strip(": ").strip()
        if isinstance(step, str):
            text = step.strip()
            if text.startswith("{") and text.endswith("}"):
                try:
                    parsed = ast.literal_eval(text)
                    if isinstance(parsed, dict):
                        return step_to_text(parsed)
                except (SyntaxError, ValueError):
                    pass
            return clean_ai_text(text, 260)
        return clean_ai_text(step, 260)

    for step in raw_steps if isinstance(raw_steps, list) else []:
        text = step_to_text(step)
        found = set(re.findall(r"\b\d{3,11}\b", text))
        if found and not found.issubset(phones):
            continue
        if text:
            cleaned.append(sanitize_unapproved_phones(text)[:260])
    return cleaned[:3]




def app_usage_chat_prompt(data):
    """Final app-help prompt for normal questions about using ScamCheck."""
    question = data.get("question", "") if isinstance(data, dict) else ""
    return f"""
Bạn là trợ lý hướng dẫn sử dụng app ScamCheck. Trả lời bằng tiếng Việt, gọi người dùng là "bác", và chỉ trả JSON hợp lệ.
Đây là câu hỏi về cách dùng app, không phải follow-up phân tích scam. Không nhắc lại vụ scam, rủi ro, OTP, ngân hàng, hotline hoặc kết quả phân tích cũ trừ khi bác hỏi trực tiếp về case đó.

Các nhóm câu hỏi app-help cần hiểu:
- Nhập/dán tin nhắn, link, email hoặc nội dung đáng nghi để phân tích.
- Tải ảnh/tệp lên chatbot hoặc khu vực kiểm tra nếu giao diện đang có nút tải ảnh/tệp.
- Đọc kết quả: mức rủi ro, bằng chứng, phần tin gốc tô vàng, bước nên làm tiếp.
- Mở lại lịch sử, tìm case cũ, xóa lịch sử hoặc xem các kiểm tra gần đây.
- Xuất/mở/chia sẻ PDF kết quả.
- Hỏi chatbot về case đang mở, gửi thêm chi tiết, hoặc hỏi cách báo cáo.
- Dùng thư viện kiểu lừa đảo, phần Q&A, luyện tập, hoặc các trang phụ nếu bác hỏi đến.

Quy tắc trả lời:
- Trước hết suy ra bác đang muốn thao tác gì trong app.
- Trả lời ngắn, trực tiếp, theo đúng giao diện ScamCheck.
- Nếu là thao tác, đưa 1-3 bước cụ thể trong next_steps.
- Nếu câu hỏi mơ hồ như "dùng sao", hãy nói cách bắt đầu nhanh nhất: nhập/dán nội dung, bấm phân tích, đọc kết quả.
- Nếu bác hỏi "mở link thế nào", không khuyến khích mở link đáng nghi; hướng dẫn dán link vào ScamCheck để kiểm tra trước.
- Không bịa nút/tính năng không chắc chắn. Nếu giao diện có thể khác, nói "nếu bác thấy nút..." hoặc hỏi 1 câu làm rõ.
- Không đưa lời khuyên scam dài nếu câu hỏi chỉ hỏi cách dùng app.

Câu hỏi của bác: {question}

Trả về JSON object:
- answer: câu trả lời chính, ngắn và dễ hiểu.
- next_steps: danh sách 0 đến 3 bước thao tác trong app.
"""


def ensure_related_bank_contact_steps(result, question, answer_text, ai_steps):
    """Ensure matched fake-bank cases include the exact official URL/contact."""
    contacts = matched_hotlines_for_case(result, question, answer_text, ai_steps, limit=1)
    if not contacts:
        return ai_steps
    context = hotline_context_blob(result, question, answer_text, ai_steps)
    if not case_has_bank_context(context):
        return ai_steps

    contact = contacts[0]
    official_url = contact.get("official_url", "")
    phone = contact.get("phone", "")
    report = contact.get("report_contact") or contact.get("report_hint") or ""
    combined = " ".join([answer_text, *ai_steps])

    if official_url and official_url not in combined:
        step = f"Kiểm tra qua kênh chính thức của {contact.get('name')}: {official_url}."
        if phone:
            step += f" Hotline: {phone}."
        if report:
            step += f" Báo cáo/hỗ trợ: {report}."
        filtered_steps = []
        for old_step in ai_steps:
            old_blob = normalize_contact_text(old_step)
            if phone and phone in old_step:
                continue
            if "website chinh thuc" in old_blob and contact.get("name", "").lower() in old_step.lower():
                continue
            filtered_steps.append(old_step)
        ai_steps = [step, *filtered_steps]
    return ai_steps[:3]


def latest_chat_case_context(data):
    """Final latest-case context for /api/chat."""
    history = data.get("history", []) if isinstance(data, dict) else []
    result = data.get("result") if isinstance(data, dict) and isinstance(data.get("result"), dict) else {}

    if not compact_result(result) and isinstance(history, list):
        result = next((row for row in history if isinstance(row, dict) and compact_result(row)), {})

    result = compact_result(result)
    evidence = result.get("evidence") if isinstance(result.get("evidence"), list) else []
    actions = result.get("next_actions") if isinstance(result.get("next_actions"), list) else []
    question = clean_ai_text(data.get("question", "") if isinstance(data, dict) else "", 900)
    support_context = support_contact_context(result, question)

    return {
        "latest_verdict": clean_ai_text(result.get("verdict_label") or result.get("zone_title") or ""),
        "latest_risk": result.get("risk", ""),
        "latest_risk_percentage": result.get("danger_score_percent", ""),
        "original_suspicious_content": clean_ai_text(result.get("checked_text") or result.get("inputText") or "", 1200),
        "latest_summary": clean_ai_text(result.get("summary", ""), 700),
        "detected_scam_signs": clean_ai_text(result.get("explanation", ""), 900),
        "uncertainty": clean_ai_text(result.get("uncertainty", ""), 500),
        "highlighted_evidence": [
            {
                "quote": clean_ai_text(row.get("quote", ""), 220),
                "why": clean_ai_text(row.get("why") or row.get("explanation") or "", 420),
            }
            for row in evidence[:4] if isinstance(row, dict)
        ],
        "previous_recommended_actions": [
            {
                "label": clean_ai_text(row.get("label", ""), 120),
                "prompt": clean_ai_text(row.get("prompt") or row.get("detail") or "", 300),
            }
            for row in actions[:3] if isinstance(row, dict)
        ],
        "user_selected_action_state": "",
        "user_extra_detail": clean_ai_text(data.get("fileText", "") if isinstance(data, dict) else "", 1000),
        "inferred_support_context": support_context,
        "matched_support_contacts": support_context.get("matched_contacts", []),
        "current_followup_question": question,
        "has_latest_case_context": bool(result),
    }


def chat_case_dossier(latest_case):
    """Final case dossier for /api/chat."""
    if not latest_case.get("has_latest_case_context"):
        return "Không có phân tích ScamCheck mới nhất đủ rõ. Hãy hỏi bác 1 câu ngắn để làm rõ vụ việc trước khi hướng dẫn."

    evidence = latest_case.get("highlighted_evidence") or []
    actions = latest_case.get("previous_recommended_actions") or []
    contacts = latest_case.get("matched_support_contacts") or []
    evidence_text = "\n".join(
        f"- Bằng chứng: {item.get('quote')}. Vì sao: {item.get('why')}"
        for item in evidence if item.get("quote") or item.get("why")
    ) or "- Chưa có bằng chứng tách riêng."
    action_text = "\n".join(
        f"- {item.get('label')}: {item.get('prompt')}"
        for item in actions if item.get("label") or item.get("prompt")
    ) or "- Chưa có bước gợi ý trước đó."
    contact_text = "\n".join(
        f"- {item.get('name')}: hotline {item.get('phone')}; official link {item.get('official_url') or 'none'}; report {item.get('report_contact') or item.get('report_hint') or 'none'}"
        for item in contacts[:3] if item.get("name") and item.get("phone")
    ) or "- Không có hotline cụ thể đã khớp cho vụ này."

    return f"""
HỒ SƠ VỤ VIỆC HIỆN TẠI CỦA BÁC:
- Kết luận mới nhất: {latest_case.get("latest_verdict") or "Chưa rõ"}.
- Mức rủi ro mới nhất: {latest_case.get("latest_risk_percentage") or "chưa rõ"}%.
- Nhóm rủi ro: {latest_case.get("latest_risk") or "chưa rõ"}.
- Nội dung đáng ngờ/tin gốc: {latest_case.get("original_suspicious_content") or "Không có văn bản gốc rõ ràng."}
- Tóm tắt phân tích: {latest_case.get("latest_summary") or "Không có tóm tắt."}
- Dấu hiệu ScamCheck đã phát hiện: {latest_case.get("detected_scam_signs") or "Không có dấu hiệu cụ thể."}
- Điểm còn cần xác minh: {latest_case.get("uncertainty") or "Không nêu."}

Bằng chứng nổi bật:
{evidence_text}

Bước ScamCheck đã gợi ý trước đó:
{action_text}

Hotline/contact liên quan đã khớp:
{contact_text}

Chi tiết/tệp bổ sung bác vừa gửi: {latest_case.get("user_extra_detail") or "Không có chi tiết/tệp bổ sung."}
Câu hỏi hiện tại của bác: {latest_case.get("current_followup_question") or "Không có câu hỏi rõ ràng."}
""".strip()


def chat_prompt(data):
    """Final contextual prompt for /api/chat."""
    latest_case = latest_chat_case_context(data)
    case_dossier = chat_case_dossier(latest_case)
    history_rows = data.get("history", []) if isinstance(data, dict) else []
    if not isinstance(history_rows, list):
        history_rows = []
    matched_contacts = latest_case.get("matched_support_contacts", [])[:3]
    context = {
        "phan_tich_moi_nhat_cua_bac": latest_case,
        "ket_qua_hien_tai": compact_result(data.get("result", {}) if isinstance(data, dict) else {}),
        "lich_su_kiem_tra_tren_thiet_bi": [compact_result(row) for row in history_rows],
        "lich_su_chat_gan_day": (data.get("messages", []) if isinstance(data, dict) else [])[-10:],
        "support_contacts_lien_quan": matched_contacts,
        "cau_hoi_moi": data.get("question", "") if isinstance(data, dict) else "",
    }
    return f"""
Bạn là ScamCheck Chat. Trả lời bằng tiếng Việt, gọi người dùng là "bác", và chỉ trả JSON hợp lệ.
You are answering a follow-up question about this exact ScamCheck case. Use the current case context first. Do not ignore it. Do not give generic advice unless the context is missing.

{case_dossier}

Quy tắc:
- Trước hết suy ra bác đang hỏi gì dựa trên HỒ SƠ VỤ VIỆC HIỆN TẠI.
- Nếu câu hỏi là follow-up như "giờ làm gì", "có nguy hiểm không", "giải thích thêm", "đã bấm link", "đã nhập OTP", "đã gửi tiền", phải bám vào đúng vụ này.
- Không phân tích lại từ đầu, không lặp toàn bộ kết quả cũ, và không đưa bài giảng chung.
- Nếu cần nói hotline/contact, chỉ dùng support_contacts_lien_quan. Chỉ nhắc 1 đến 2 contact thật sự liên quan.
- Nếu vụ việc là fake bank/phishing ngân hàng và support_contacts_lien_quan có official_url, hãy đưa official_url của đúng ngân hàng đó như nơi bác tự kiểm tra. Nếu có report_contact/report_hint, có thể thêm 1 cách báo cáo phù hợp.
- Nếu support_contacts_lien_quan rỗng, không liệt kê ví dụ ngân hàng. Chỉ nói bác kiểm tra kênh chính thức trong app/thẻ/website nếu thật sự cần.
- Không tự thêm danh sách mặc định kiểu Vietcombank/BIDV/VietinBank/Agribank, Công an 113, 156, 5656 trừ khi vụ việc hoặc câu hỏi trực tiếp liên quan.
- Nếu có số phần trăm rủi ro trong context, giữ nguyên dạng số phần trăm, ví dụ 92%.
- Nếu bác đã bấm link, chuyển tiền, nhập OTP/mật khẩu/CCCD/số thẻ, ưu tiên bước chặn thiệt hại ngay.
- Nếu context cho thấy an toàn hoặc rủi ro thấp, giải thích bình tĩnh và không cảnh báo quá mức.
- Câu trả lời phải ngắn, thực tế; next_steps là 0 đến 3 chuỗi văn bản sạch, không trả object/dict/code.

Bối cảnh JSON:
{json.dumps(context, ensure_ascii=False)}

Trả về JSON object:
- answer: câu trả lời chính.
- next_steps: danh sách 0 đến 3 bước ngắn.
"""


def analysis_prompt(message):
    """Final first-pass Gemini prompt with explicit typo-domain detection."""
    return f"""
Bạn là Thám tử ScamCheck. Chỉ trả về JSON hợp lệ bằng tiếng Việt có dấu, không markdown.
Phân tích tin nhắn/link/ảnh để chấm riskpercentage từ 0 đến 100.

Luật chấm điểm:
- Thấp khi nội dung đời thường, rõ nguồn, không link lạ, không tiền, không OTP/mật khẩu/CCCD.
- Trung bình khi thiếu ngữ cảnh, người gửi chưa xác minh, có thúc giục hoặc có chi tiết cần kiểm tra.
- Cao khi có mạo danh, link lạ, chuyển tiền/phí, OTP/mật khẩu, CCCD, tải app, đe dọa hoặc tạo áp lực gấp.
- Luôn kiểm tra tên miền giả mạo và typo-squatting. Tên miền sai chính tả, thêm/bớt/gạch nối ký tự, subdomain gây hiểu nhầm, hoặc gần giống ngân hàng/cơ quan nhưng không phải domain chính thức đều là dấu hiệu mạnh.
- Ví dụ phải coi là đáng ngờ: vietconbank, vietcom-bank, vietcombank-login, vpbonk, vp-bank-login, acb-secure, bidv-login, techcombank-secure nếu không phải domain chính thức.
- Nếu nội dung nhắc một ngân hàng/công ty nhưng link thuộc miền khác hoặc gần giống tên đó, hãy nêu rõ đây có thể là link giả mạo.
- Không dùng điểm mặc định. Điểm phải dựa trên chi tiết thật sự xuất hiện trong nội dung.

Yêu cầu nội dung:
- summary: 1 câu kết luận trực tiếp.
- explanation: 3-5 câu ngắn, giải thích vì sao điểm rủi ro như vậy, nhắc domain giả mạo nếu có.
- uncertainty: 1-2 câu về điều còn cần xác minh.
- evidence: 2-4 mục quan trọng nhất, mỗi mục có quote ngắn nguyên văn và why chi tiết.
- next_actions: đúng 3 bước, mỗi bước có label ngắn và prompt 1-2 câu, phụ thuộc trực tiếp vào case.
- rescue_options: chỉ tạo khi có khả năng lừa đảo hoặc cần xử lý; 3-5 lựa chọn dựa trên nội dung.
Không bịa số điện thoại, link, ngân hàng hoặc cơ quan không có trong nội dung.

Trả về đúng JSON object gồm:
riskpercentage, summary, explanation, uncertainty, evidence, next_actions, rescue_options.

Nội dung:
{message or "(The user uploaded an image. Read the image and analyze it.)"}
"""


# Web pages and API endpoints used by static/app.js.
@app.route("/")
def home():
    """Serve the single-page app shell.

    The template contains all visible pages, and JavaScript switches between
    them in the browser. Sample messages are injected here for the home screen.
    """
    return render_template("index.html", samples=SAMPLE_MESSAGES)


@app.route("/api/analyze", methods=["POST"])
def analyze():
    """Analyze a message/image and return a normalized ScamCheck result.

    Request JSON can contain message text and/or an image data object. The route
    validates input length, calls Gemini, cleans the result, and includes server-
    rendered HTML so the frontend can display the card immediately.
    """
    # Text and image inputs both go through the same Gemini prompt so the UI stays simple.
    data = read_body()
    message = str(data.get("message", "")).strip()
    image = data.get("image")
    if not message and not image:
        return jsonify({"error": "Vui lòng nhập tin nhắn, link, giọng nói hoặc tải ảnh."}), 400
    if prompt_is_too_long(message):
        return too_long_error()
    try:
        result = clean_result(ask_gemini(analysis_prompt(message), image), message)
        result["html"] = result_html(result)
    except Exception as error:
        return jsonify({
            "error": friendly_gemini_error(error),
            "detail": str(error)[:500],
        }), 503
    return jsonify(result)


@app.route("/api/analysis-followup", methods=["POST"])
def analysis_followup():
    """Return delayed Cô tâm lý HTML after the main analysis has rendered.

    The main analysis should appear fast. This route lets the UI ask for the
    softer psychology note afterward only when the risk score is high enough.
    """
    data = read_body()
    result = restore_result(data.get("result", {}))
    message = str(data.get("message") or result.get("checked_text") or "").strip()
    image = data.get("image")
    if not needs_followup(result):
        result["html"] = result_html(result)
        return jsonify(result)
    try:
        result = add_psychology_if_needed(result, message, image)
    except Exception:
        result["psychology_error"] = "Cô tâm lý đang bận, bác có thể tiếp tục theo các bước bên trên."
    result["html"] = result_html(result)
    return jsonify(result)


@app.route("/api/chat", methods=["POST"])
def chat():
    """Answer follow-up questions in the floating chatbot.

    The route can use a question, image, uploaded file text, current result, and
    recent history. It sanitizes phone numbers so the model cannot invent unsafe
    support contacts.
    """
    data = read_body()
    question = str(data.get("question", "")).strip()
    image = data.get("image")
    file_text = str(data.get("fileText", "")).strip()
    if not question and not image and not file_text:
        return jsonify({"error": "Vui lòng nhập câu hỏi hoặc tải thêm ảnh/file."}), 400
    if prompt_is_too_long(question, file_text):
        return too_long_error()
    data = chat_data_with_latest_case(data)
    try:
        app_usage = is_app_usage_question(question)
        answer = ask_gemini(app_usage_chat_prompt(data) if app_usage else chat_prompt(data), image)
        result = data.get("result", {})
        answer_data = answer if isinstance(answer, dict) else {}
        answer_text = clean_ai_text(sanitize_unapproved_phones(answer_data.get("answer", ""))).strip()
        ai_steps = clean_chat_steps(answer_data.get("next_steps"))
        if not app_usage:
            ai_steps = ensure_related_bank_contact_steps(result, question, answer_text, ai_steps)
        merged_steps = []
        for step in ai_steps:
            if step not in merged_steps:
                merged_steps.append(step)
        return jsonify({
            "source": "gemini",
            "answer": answer_text,
            "next_steps": merged_steps[:3],
        })
    except Exception as error:
        return jsonify({
            "error": friendly_gemini_error(error),
            "detail": str(error)[:500],
        }), 503


@app.route("/api/share-result", methods=["POST"])
def share_result():
    """Store a result and return a shareable /analysis/<id> URL."""
    result = share_result_payload(read_body().get("result", read_body()))
    return jsonify({
        **result,
        "share_url": f"/analysis/{result['share_id']}",
    })


@app.route("/api/shared-result/<share_id>")
def shared_result(share_id):
    """Return a stored result for a public analysis URL.

    share_id is sanitized before lookup so a malicious URL cannot escape the
    JSON file store or inject special characters into the response.
    """
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", share_id)
    result = load_shared_results().get(clean_id)
    if not result:
        return jsonify({"error": "Không tìm thấy kết quả đã chia sẻ."}), 404
    result = restore_result(result)
    result["share_id"] = clean_id
    result["html"] = result_html(result)
    return jsonify(result)


@app.route("/api/history")
def persistent_history():
    """Return the permanent analysis history stored on the app server."""
    return jsonify({"history": shared_history_items()})


@app.route("/api/history", methods=["DELETE"])
def delete_persistent_history():
    """Delete all saved analysis history from the app server.

    This is called by the Xóa hết button. It clears the JSON file database, then
    the frontend also clears browser localStorage.
    """
    save_shared_results({})
    return jsonify({"ok": True})


@app.route("/api/history/<history_id>", methods=["DELETE"])
def delete_persistent_history_item(history_id):
    """Delete one saved analysis result by share id or result id."""
    clean_id = re.sub(r"[^a-zA-Z0-9_-]", "", history_id)
    shared = load_shared_results()
    removed = False

    if clean_id in shared:
        shared.pop(clean_id, None)
        removed = True
    else:
        for share_id, result in list(shared.items()):
            if isinstance(result, dict) and str(result.get("id")) == clean_id:
                shared.pop(share_id, None)
                removed = True
                break

    save_shared_results(shared)
    return jsonify({"ok": True, "removed": removed})


@app.route("/api/result-pdf", methods=["POST"])
def result_pdf():
    """Download the current result as a Vietnamese multi-page PDF."""
    result = restore_result(read_body().get("result", read_body()))
    try:
        pdf_file = build_result_pdf(result)
    except Exception:
        pdf_file = build_fallback_result_pdf(result)
    preview = request.args.get("preview") == "1"
    return send_file(
        pdf_file,
        mimetype="application/pdf",
        as_attachment=not preview,
        download_name="scamcheck-ket-qua.pdf",
    )


@app.route("/api/library")
def library():
    """Return scam-library entries for the Thư viện kiểu lừa đảo screen."""
    return jsonify(SCAM_LIBRARY)


@app.route("/api/training")
def training():
    """Return practice questions for the Luyện tập screen."""
    return jsonify(TRAINING_MESSAGES)


@app.route("/api/hotlines")
def hotlines():
    """Return approved hotline numbers used by chat and rescue mode."""
    return jsonify(HOTLINES)


@app.route("/api/transcribe", methods=["POST"])
def transcribe():
    """Transcribe uploaded microphone audio with Deepgram Vietnamese speech-to-text.

    The browser records audio and posts it as a file named audio. The backend
    forwards the bytes to Deepgram and returns only the transcript text.
    """
    key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    audio = request.files.get("audio")
    if not key:
        return jsonify({"error": "Chưa cấu hình DEEPGRAM_API_KEY trong file .env."}), 503
    if not audio:
        return jsonify({"error": "Chưa nhận được âm thanh để ghi."}), 400

    content_type = audio.mimetype or "audio/webm"
    response = requests.post(
        "https://api.deepgram.com/v1/listen?model=nova-3&language=vi&smart_format=true",
        headers={
            "Authorization": f"Token {key}",
            "Content-Type": content_type,
        },
        data=audio.read(),
        timeout=45,
    )
    if response.status_code >= 400:
        return jsonify({
            "error": "Deepgram chưa nhận diện được giọng nói lúc này.",
            "detail": response.text[:300],
        }), 503

    data = response.json()
    transcript = (
        data.get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])[0]
        .get("transcript", "")
        .strip()
    )
    return jsonify({"text": transcript})


@app.route("/api/rescue", methods=["POST"])
def rescue():
    """Return urgent next steps for users who may already have acted.

    Rescue mode uses the result's rescue_options so the steps match the current
    scam. If Gemini fails, the route returns a local fallback because this part
    should still work during an urgent situation.
    """
    # Rescue mode is allowed to fall back locally because users may need urgent steps.
    data = read_body()
    raw_options = data.get("situations")
    selected_ids = [str(value).strip() for value in raw_options] if isinstance(raw_options, list) else [str(data.get("situation", "")).strip()]
    selected_ids = list(dict.fromkeys(value for value in selected_ids if value))
    result = data.get("result", {})
    options = clean_rescue_options(result.get("rescue_options"))
    option_map = {option["id"]: option for option in options}
    selected_options = [option_map[option_id] for option_id in selected_ids if option_id in option_map]
    if not selected_options:
        return jsonify({"error": "Vui lòng chọn tình huống từ gợi ý AI của kết quả này."}), 400
    fallback_steps = [
        "1. Dừng mọi thao tác với người gửi và giữ lại tin nhắn, ảnh chụp, đường link hoặc biên lai liên quan. Câu nói mẫu: Tôi cần kiểm tra lại vụ việc trước khi làm tiếp.",
        "2. Nếu có liên quan tài khoản hoặc tiền, liên hệ ngân hàng qua số chính thức trong ứng dụng/thẻ hoặc danh sách hỗ trợ. Câu nói mẫu: Tôi nghi có rủi ro lừa đảo, xin kiểm tra và khóa giao dịch nếu cần.",
        "3. Nếu đã lộ giấy tờ, mã xác thực hoặc bị đe dọa, báo cho người thân và cơ quan chức năng phù hợp. Câu nói mẫu: Tôi muốn trình báo việc nghi bị lừa đảo và có bằng chứng kèm theo.",
    ]
    try:
        data = ask_gemini(rescue_prompt(selected_options, result, HOTLINES))
        steps = clean_rescue_steps(data.get("steps", [])) if isinstance(data, dict) else []
        return jsonify({"source": "gemini", "steps": steps or fallback_steps})
    except Exception:
        return jsonify({"source": "fallback", "steps": fallback_steps})


@app.route("/api/history-view", methods=["POST"])
def history_view():
    """Rebuild HTML for an older local-history item.

    Some browser history entries may not already contain fresh HTML. This route
    restores the result shape and renders the current card layout for it.
    """
    try:
        result = restore_result(read_body())
        result["html"] = result_html(result)
        return jsonify(result)
    except Exception:
        return jsonify({"error": "Kết quả cũ không còn đủ dữ liệu để mở lại."}), 400


@app.route("/<path:client_path>")
def client_route(client_path):
    """Serve the app shell for shareable browser paths after API routes are tried.

    Routes such as /analysis/<share_id> are handled by JavaScript after the app
    shell loads. API-looking paths still return a real 404 JSON response.
    """
    if client_path.startswith("api/"):
        return jsonify({"error": "API route not found."}), 404
    return render_template("index.html", samples=SAMPLE_MESSAGES)


if __name__ == "__main__":
    # Local development entry point. PythonAnywhere imports app via WSGI, so this
    # block only runs when students start the app directly with python app.py.
    debug = os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    https = os.getenv("SCAMCHECK_HTTPS", "").lower() in {"1", "true", "yes"}
    app.run(
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 5001)),
        debug=debug,
        ssl_context="adhoc" if https else None,
    )
