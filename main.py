import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
from bs4 import BeautifulSoup
import logging

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
        title_element = soup.select_one("#bible_text") 
        sub_title_element = soup.select_one("#bibleinfo_box") 
        
        title_text = title_element.get_text(strip=True) if title_element else "제목 없음"
        
        # [수정] 본문 정보 가져오기 및 텍스트 후처리
        # 사이트 원문 예시: "본문 : 시편 1:1-6 (찬송 : 1장)"
        bible_ref = sub_title_element.get_text(strip=True) if sub_title_element else "본문 정보 없음"
        
        # [수정] 포맷팅 개선: 불필요한 텍스트 제거 및 줄바꿈 처리
        if bible_ref:
            # 1. "본문 :" 제거 (중복 방지)
            bible_ref = bible_ref.replace("본문 :", "").replace("본문:", "").strip()
            
            # 2. "(찬송" 패턴을 찾아서 줄바꿈(\n) + "찬송가"로 변경하고 닫는 괄호 ")" 제거
            # 결과 예시: "시편 1:1-6\n찬송가 : 1장"
            bible_ref = bible_ref.replace("(찬송", "\n찬송가").replace(")", "")

        # 2. 해설 파싱 (수정된 로직: 나의 적용, 기도하기 제외)
        body_cont = soup.select_one(".body_cont")
        
        commentary_text = ""
        if body_cont:
            skip_section = False # 특정 섹션 스킵을 위한 플래그
            
            for child in body_cont.find_all("div", recursive=False):
                text = child.get_text(separator="\n", strip=True)
                if not text:
                    continue
                
                classes = child.get("class", [])
                
                if "b_text" in classes:
                    # 묵상 서론
                    commentary_text += text + "\n\n"
                    
                elif "g_text" in classes:
                    # 소제목 (성경 이해, 나의 적용, 기도하기 등)
                    # "나의 적용"과 "기도하기"는 제외
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
            "bible_ref": bible_ref,
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
    
    # -- 헤더 생성 --
    # [수정] bible_ref에 이미 줄바꿈과 포맷팅이 적용됨
    header = f"✝오늘의 QT(순)✝\n\n[{qt_data['title']}]\n{qt_data['bible_ref']}\n\n"
    
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
    # [수정] "해설 전문 보기:" 다음에 줄바꿈(\n) 추가
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
    return {"message": "KakaoTalk QT Bot Server (Formatting Update Ver) is Running!"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)