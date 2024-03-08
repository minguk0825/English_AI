from fastapi import FastAPI, HTTPException, Query,File,UploadFile
import httpx
from httpx import Timeout
import boto3
from botocore.exceptions import NoCredentialsError
import uuid
from pydub import AudioSegment

app = FastAPI()
api_key = ""

# AWS 설정
AWS_ACCESS_KEY_ID = ""
AWS_SECRET_ACCESS_KEY = ""
AWS_REGION = ""
S3_BUCKET = ""

s3_client = boto3.client('s3', region_name=AWS_REGION,
                         aws_access_key_id=AWS_ACCESS_KEY_ID,
                         aws_secret_access_key=AWS_SECRET_ACCESS_KEY)

@app.post("/api/generate_conversation")
async def generate_conversation(location: str = Query(..., description="Enter a location")):

    # 고유 ID 생성
    file_id_1 = str(uuid.uuid4())
    file_id_2 = str(uuid.uuid4())
    file_id_3 = str(uuid.uuid4())
    
    # 장소에 따른 상황 생성 프롬프트
    situation_prompt = f"Please list one possible situation at a {location}, in one sentence. Give me something different than the answer you gave me before."

    # 대화 생성 프롬프트
    conversation_prompt_template = ("Situation: {situation}\n"
                                    "situations are like the above. print out a conversation script between two people. "
                                    "The length of the script should be about 2 sentences. Give me something different than the answer you gave me before and Please leave out the greetings as they may be too similar.")

    timeout = Timeout(60.0, connect=60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # 상황 생성 요청
        situation_response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": "gpt-3.5-turbo-0301",
                "messages": [{"role": "user", "content": situation_prompt}],
                "temperature": 0.7
            },
            headers={"Authorization": "Bearer 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"}
        )

        if situation_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Error in OpenAI request for situation generation")

        situations = situation_response.json().get("choices", [{}])[0].get("message", "No response")

        # 대화 생성 요청
        conversation_response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json={
                "model": "gpt-3.5-turbo",
                "messages": [{"role": "user", "content": conversation_prompt_template.format(situation=situations)}],
                "temperature": 0.7
            },
            headers={"Authorization": "Bearer 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"}
        )

        if conversation_response.status_code != 200:
            raise HTTPException(status_code=400, detail="Error in OpenAI request for conversation generation")

        conversation = conversation_response.json().get("choices", [{}])[0].get("message", "No response")    

    ## brute force 알고리즘을 활용하여 text 쪼개기
    def split_by_newline(text):
        parts = []
        current_part = ""
        for char in text:
            if char == "\n":
                parts.append(current_part)
                current_part = ""
            else:
                current_part += char
        parts.append(current_part)  # 마지막 부분 추가
        return parts
    conversation_part = split_by_newline(conversation["content"])
    first_text = conversation_part[0]
    second_text = conversation_part[1]


    # 음성 파일 생성 및 로컬 저장
    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "tts-1",
            "voice": "alloy",
            "input": first_text
        }
        response = await client.post(
            "https://api.openai.com/v1/audio/speech", headers=headers, json=data)
        audio_data = response.content

        file_path = f'speech{file_id_1}.mp3'
        with open(file_path, "wb") as f:
            f.write(audio_data)

    

    # 음성 파일 생성 및 로컬 저장
    async with httpx.AsyncClient() as client:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "tts-1",
            "voice": "onyx",
            "input": second_text
        }
        response = await client.post(
            "https://api.openai.com/v1/audio/speech", headers=headers, json=data)
        audio_data = response.content

        file_path = f'speech{file_id_2}.mp3'
        with open(file_path, "wb") as f:
            f.write(audio_data)

    sound1 = AudioSegment.from_mp3(f"speech{file_id_1}.mp3")
    sound2 = AudioSegment.from_mp3(f"speech{file_id_2}.mp3")
    combined = sound1 + sound2
    combined_file_path = f"combined{file_id_3}.mp3"
    combined.export(combined_file_path, format="mp3")

    # S3에 업로드
    try:
        with open(combined_file_path, "rb") as f:
            s3_client.upload_fileobj(f, S3_BUCKET, f"{file_id_3}.mp3")
    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="AWS credentials not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


    return {
        "file_id_3":file_id_3,
        "situations": situations,
        "conversation": conversation
    }
## pip install fastapi httpx boto3 python-multipart uvicorn 명령어를 통해 필요 파일 설치
## uvicorn main:app 명령어를 통해 서버 실행