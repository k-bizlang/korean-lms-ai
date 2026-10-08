import os
import json
import logging
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
import pandas as pd

# 📌 로깅 설정 (접속 이력 및 모니터링용)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔑 검증된 안정적인 Gemini API 키 및 클라이언트 설정
API_KEY = "AQ.Ab8RN6JZsg1xf6Ptjx3fSDXxJB9L6g9GlR1DM1QJEc4vRCV8VA"
client = genai.Client(api_key=API_KEY)

# 📌 1. config.json 파일에서 센터 승인 및 체험판/풀버전 설정 불러오기
def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"config.json 읽기 에러: {e}")
    # 기본 폴백 설정 (체험판 ID)
    return {
        "DEMO_TRIAL_01": {
            "academy_name": "글로벌 직무 한국어 체험 센터",
            "target_language": "베트남어",
            "is_approved": True,
            "max_chapter_limit": 1
        }
    }

# 📌 2. 장별/과별 공식 구글 드라이브 파일 ID 폴백 딕셔너리
MANAGER_DEFAULT_FILE_IDS = {
    1: "1on7JrpM4wdKwYqMMNvIs-djFSNZdhN8A", 2: "1WSc7EC8LqnAYyHSHi2dcGkFtqwwOePXs",
    3: "1i3S704xhel-CMo-iWpTeQKJsr9MK9yyj", 4: "1S2X_H6e3XsG5zNSUxr7yEm8LWZwQObmc",
    5: "1Oh_m47emmxbcopfbnf23CY53Us4NqvBv", 6: "1qBqBZETsx_cDnYHQdPawV421FVwnNS8n",
    7: "1yvC0kI4d0dAbLi_O_xF4OyCMZZIRWEsw", 8: "1pEM1ljl7K9rQySNaynfS31YdLX-7tnV9",
    9: "1_ppFdMaH3_kPxfOfgKlnjCrkAfSIGPxb", 10: "1T0k4t98YnvEwNFuepQMEuDNeDVNgZOnJ",
    11: "1uPXdQX40silkHl30NnjYeJ1E6YjwySqN", 12: "1IZsCYbNGlnJWo6YQvVv1zAL1iMWugCD2",
    13: "1JA1DQ2tgedmjxXm9uKN_1W_3PuHjZKsK", 14: "1LIQcxUIgI71ZE3Py_uZp-UklT1pAb9Av",
    15: "1gl02DQ3N9Mkc1M9VlmX04SX2ITQFYEtI", 16: "1chamQ4k5uW7xIOEWIFVNdfyFOOQ1TpCR"
}

CONSULTANT_DEFAULT_FILE_IDS = {
    1: "1-GglR8iUJ03NyFHtXRNchMohXg3imvTw", 2: "1YIc0ZIS7NEhjf1fijFaaa_4WD1XyKAIp",
    3: "1lJPV3i_beLHjiHVEzw8K_sXaYGc6B1-6", 4: "1CI1wJBhP-v40iEcMmtJttEwefK7Hyo13",
    5: "17zQ6Btk8zTbTpXy2IjM18WYXAWwFLJnT", 6: "1UHI6Vvvv_ptWWaPL9hWJ4LLOQB9u78Sd",
    7: "1nZRILkspeyprgfQDvUTrbcSTxA6EsGuI", 8: "13trnGbLIDYXRwlItlH8D1aQQvJIrH877",
    9: "1VuIYkuQvKEkbcY8GkSqtGUz7bU_oqsAE", 10: "1Ospd1bCMCfqkHXlDWb2YRoPZNuKnc6gQ",
    11: "1rsNUKaAVQVPDeIKmUAo8gUOJ6qKxqBJe", 12: "1SmFwuPFquBxX_5u8K-7eQFXWPGfo8CBO",
    13: "1xFrouhEaDLyHY-ABcn4U0L0TWxEh94OS", 14: "1ev3ZqKQek71Q2hCrjwJysylTuNZftsRz"
}

def load_curriculum_csv():
    csv_path = os.path.join(os.path.dirname(__file__), "curriculum.csv")
    if not os.path.exists(csv_path):
        return pd.DataFrame()
    try:
        df = pd.read_csv(csv_path, encoding='utf-8-sig', quotechar='"', on_bad_lines='skip')
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df
    except Exception as e:
        logging.error(f"CSV 로딩 에러: {e}")
        return pd.DataFrame()

# 📌 3. 센터 ID 승인 검증 및 강의 데이터 연동 API
@app.get("/api/lesson-data")
async def get_lesson_data(
    academy_code: str = Query(...), 
    course_type: str = "manager", 
    chapter: int = 1, 
    page: int = 1,
    client_lang: str = "ko"
):
    configs = load_config()
    clean_code = str(academy_code).strip()
    
    if clean_code not in configs or not configs[clean_code].get("is_approved", False):
        raise HTTPException(status_code=403, detail="승인되지 않았거나 존재하지 않는 센터 ID입니다. 올바른 ID를 입력해 주세요.")
    
    academy_info = configs[clean_code]
    max_limit = academy_info.get("max_chapter_limit")
    
    logging.info(f"📥 [접속 승인 완료] 센터명: {academy_info['academy_name']} ({clean_code}) | 감지 언어: {client_lang}")

    raw_type = str(course_type).lower().strip()
    c_type = "consultant" if "consultant" in raw_type or "컨설턴트" in raw_type else "manager"
    
    absolute_max_chapter = 16 if c_type == "manager" else 14
    allowed_max_chapter = 1 if max_limit == 1 else absolute_max_chapter
    
    final_chapter = max(1, min(int(chapter), allowed_max_chapter))
    final_page = max(1, int(page))
  
    chapter_title = f"[{c_type.upper()}] 제{final_chapter}장 직무 교육"
    page_content_text = "현재 페이지의 강의 대본을 준비 중입니다."
    
    if c_type == "manager":
        drive_file_id = MANAGER_DEFAULT_FILE_IDS.get(final_chapter, "1on7JrpM4wdKwYqMMNvIs-djFSNZdhN8A")
    else:
        drive_file_id = CONSULTANT_DEFAULT_FILE_IDS.get(final_chapter, "1-GglR8iUJ03NyFHtXRNchMohXg3imvTw")

    df_curriculum = load_curriculum_csv()
    if not df_curriculum.empty:
        try:
            df_curriculum['chapter_num'] = pd.to_numeric(df_curriculum['chapter_num'], errors='coerce')
            df_curriculum['page_num'] = pd.to_numeric(df_curriculum['page_num'], errors='coerce')
            
            matched = df_curriculum[
                (df_curriculum['course_type'].astype(str).str.strip().str.lower() == c_type) & 
                (df_curriculum['chapter_num'] == final_chapter) & 
                (df_curriculum['page_num'] == final_page)
            ]
            
            if not matched.empty:
                row = matched.iloc[0]
                if pd.notna(row.get('chapter_title')):
                    chapter_title = str(row['chapter_title']).strip()
                if pd.notna(row.get('page_content_text')):
                    page_content_text = str(row['page_content_text']).strip()
                if pd.notna(row.get('drive_file_id')) and str(row.get('drive_file_id')).strip() != "":
                    drive_file_id = str(row.get('drive_file_id')).strip()
        except Exception as e:
            logging.error(f"CSV 검색 에러: {e}")
  
    return {
        "academy_code": clean_code,
        "academy_name": academy_info["academy_name"],
        "target_language_auto": client_lang,
        "course_type": c_type,
        "chapter": final_chapter,
        "page": final_page,
        "max_chapter": allowed_max_chapter,
        "chapter_title": chapter_title,
        "page_content_text": page_content_text,
        "drive_file_id": drive_file_id,
        "is_trial": (max_limit == 1)
    }

# 📌 4. Gemini AI 튜터 API
class QuestionRequest(BaseModel):
    academy_code: str
    course_type: str
    chapter_title: str
    current_page: int
    page_content_text: str
    student_message: str
    client_lang: str = "ko"

@app.post("/api/ai-tutor")
async def ai_tutor_gateway(data: QuestionRequest):
    configs = load_config()
    clean_code = str(data.academy_code).strip()
    if clean_code not in configs or not configs[clean_code].get("is_approved", False):
        raise HTTPException(status_code=403, detail="인증되지 않은 접근입니다.")
        
    academy_info = configs[clean_code]
    user_lang = data.client_lang if data.client_lang else "ko"
    
    msg = data.student_message.strip()
    if not msg:
        return {"reply": "질문 내용을 입력해 주세요."}

    system_prompt = (
        f"당신은 직무 한국어 교육 기관의 수석 교사 '지니 선생님'입니다.\n"
        f"교육생 접속 언어 환경: {user_lang}\n"
        f"현재 수업 위치: {data.chapter_title} (페이지 {data.current_page})\n"
        f"현재 페이지 참고 대본: \"{data.page_content_text}\"\n\n"
        f"지침:\n"
        f"1. 말투는 사람이 듣기에 온화하고 차분하며 거부감이 전혀 없는 다정한 어조로 답변하세요.\n"
        f"2. 교육생의 질문에 대해 현재 페이지 대본을 바탕으로 한국어로 명쾌하게 설명해 주세요.\n"
        f"3. 교육생이 완벽히 이해할 수 있도록 접속 환경 언어({user_lang})를 고려한 번역과 설명을 함께 병기해 주세요."
    )
    
    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=f"{system_prompt}\n\n교육생 질문: {msg}"
        )
        
        if response and response.text:
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                total_t = response.usage_metadata.total_token_count
                logging.info(f"📊 [AI 토큰 소모량] 센터:{clean_code} | 총 토큰: {total_t}")
                
            return {"reply": response.text}
            
    except Exception as e:
        logging.error(f"Gemini API 에러: {e}")
        
    return {"reply": "죄송합니다. 일시적인 통신 장애로 답변을 생성하지 못했습니다."}

# 📌 5. 루트 화면 연결 (HTML 응답)
from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
async def read_root():
    if os.path.exists("index.html"):
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    return "index.html not found"