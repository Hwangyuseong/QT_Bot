import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
from bs4 import BeautifulSoup
import logging
import re  # 정규표현식 모듈 추가

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# 매일성경 순 (청소년/청년용) URL (?qt_ty=QT6)
QT_URL = "https://sum.su.or.kr:8888/bible/today?qt_ty=QT6"

async def fetch_qt_data():
    """
    매일성경 순(QT6) 내용을 크롤링합니다.
    (HTML 구조: .body_cont > .b_text, .g_text, .text 파싱)
    """
    try:
        # User-Agent 헤더 추가
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
            response = await client.get(QT_URL)
            response.raise_for_status()
            
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. 날짜 및 제목 추출
        # [수정] ID 선택자(#) 대신 Class 선택자(.) 사용 (HTML 구조 변경 대응)
        # 예: <div class="bible_text">...</div>
        title_element = soup.select_one(".bible_text") 
        # 예: <div class="bibleinfo_box" id="bibleinfo_box_3">...</div> (ID가 동적이므로 클래스로 접근)
        sub_title_element = soup.select_one(".bibleinfo_box") 
        
        title_text = title_element.get_text(strip=True) if title_element else "제목 없음"
        
        # [수정] 정규식으로 본문과 찬송 정보 정확히 분리하기
        raw_info = sub_title_element.get_text(strip=True) if sub_title_element else ""
        
        bible_range = "본문 정보 없음"
        hymn_text = "-"
        
        # [수정] 정규식 패턴 개선: 괄호 유무와 '찬송'/'찬송가' 변형 모두 대응
        # 패턴 설명:
        # 본문\s*[:]?\s* -> "본문" 글자와 선택적 콜론
        # (.*?) -> 본문 내용 (그룹 1)
        # \s*[(]?찬송(?:가)?\s*[:]?\s* -> 공백, 여는괄호(옵션), "찬송" 또는 "찬송가", 콜론(옵션)
        # (.*?)[)]?$ -> 찬송가 내용 (그룹 2), 닫는괄호(옵션), 문자열 끝
        match = re.search(r"본문\s*[:]?\s*(.*?)\s*[(]?찬송(?:가)?\s*[:]?\s*(.*?)[)]?$", raw_info)
        
        if match:
            bible_range = match.group(1).strip()
            hymn_text = match.group(2).strip()
        else:
            # 패턴 매칭 실패 시 단순 처리
            bible_range = raw_info.replace("본문 :", "").replace("본문:", "").strip()

        # 2. 해설 파싱 (나의 적용, 기도하기 제외)
        body_cont = soup.select_one(".body_cont")
        
        commentary_text = ""
        if body_cont:
            skip_section = False 
            
            for child in body_cont.find_all("div", recursive=False):
                text = child.get_text(separator="\n", strip=True)
                if not text:
                    continue
                
                classes = child.get("class", [])
                
                if "b_text" in classes:
                    # 묵상 서론
                    commentary_text += text + "\n\n"
                    
                elif "g_text" in classes:
                    # "나의 적용", "기도하기" 제외
                    if "나의 적용" in text or "기도하기" in text:
                        skip_section = True
                    else:
                        skip_section = False
                        commentary_text += f"📖 {text}\n"
                    
                elif "text" in classes:
                    # 본문 내용
                    if not skip_section:
                        commentary_text += text + "\n\n"
        else:
            commentary_text = "해설 내용을 불러올 수 없습니다."

        if not commentary_text.strip():
             commentary_text = "해설 내용을 찾을 수 없습니다 (HTML 구조 변경 가능성)."

        return {
            "title": title_text,
            "bible_range": bible_range,
            "hymn": hymn_text,
            "commentary": commentary_text,
            "url": QT_URL
        }

    except Exception as e:
        logger.error(f"QT 크롤링 실패: {str(e)}")
        return None

@app.post("/qt")
async def get_qt(request: Request):
    """
    카카오톡 스킬 서버 엔드포인트
    """
    qt_data = await fetch_qt_data()

    if not qt_data:
        return JSONResponse(content={
            "version": "2.0",
            "template": {
                "outputs": [
                    {
                        "simpleText": {
                            "text": "죄송합니다. 큐티 정보를 가져오는데 실패했습니다."
                        }
                    }
                ]
            }
        })

    # --- 카카오톡 응답 생성 ---
    outputs = []
    
    # -- 헤더 생성 (요청하신 포맷 적용) --
    # [타이틀]
    # 본문: ...
    # 찬송: ...
    header = f"✝오늘의 QT(순)✝\n\n[{qt_data['title']}]\n본문: {qt_data['bible_range']}\n찬송: {qt_data['hymn']}\n\n"
    
    full_commentary = qt_data['commentary']
    
    # 첫 번째 말풍선 길이 제한
    limit_len = 950 - len(header)
    
    part_1 = full_commentary[:limit_len]
    part_2 = full_commentary[limit_len:] 
    
    # 1. 첫 번째 말풍선
    outputs.append({
        "simpleText": {
            "text": header + part_1
        }
    })
    
    # 2. 두 번째 말풍선
    if part_2:
        if len(part_2) > 1000:
             part_2 = part_2[:950] + "\n...(내용 더 있음)"
             
        outputs.append({
            "simpleText": {
                "text": part_2
            }
        })

    # 3. 세 번째 말풍선 (링크 및 인사말)
    footer_msg = f"🔗 해설 전문 보기:\n{qt_data['url']}\n\n🌟아침에 말씀으로 시작하며 하나님의 은혜 충만으로 하루를 시작해 보아요🌟"
    outputs.append({
        "simpleText": {
            "text": footer_msg
        }
    })

    response_body = {
        "version": "2.0",
        "template": {
            "outputs": outputs,
            "quickReplies": [
                 {
                    "messageText": "오늘의 QT",
                    "action": "message",
                    "label": "🔄 다시보기"
                }
            ]
        }
    }

    return JSONResponse(content=response_body)

@app.get("/")
async def root():
    return {"message": "KakaoTalk QT Bot Server (Formatting Final Ver) is Running!"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)