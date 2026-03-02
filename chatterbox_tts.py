"""Chatterbox TTS API - Text-to-speech with voice cloning on Modal."""

import os
import tempfile
import modal

# Use this to add Supabase S3 credentials in Modal:
# modal secret create supabase-s3 \
#   AWS_ACCESS_KEY_ID=<supabase-s3-access-key-id> \
#   AWS_SECRET_ACCESS_KEY=<supabase-s3-secret-access-key>

# Use this to test locally:
# modal run chatterbox_tts.py \
#   --prompt "Hello from Chatterbox [chuckle]." \
#   --voice-key "voices/system/<voice-id>"

# Use this to test CURL:
# curl -X POST "https://<your-modal-endpoint>/generate" \
#   -H "Content-Type: application/json" \
#   -H "X-Api-Key: <your-api-key>" \
#   -d '{"prompt": "Hello from Chatterbox [chuckle].", "voice_key": "voices/system/<voice-id>"}' \
#   --output output.wav

# Supabase S3 storage config
SUPABASE_S3_SECRET_NAME = os.environ.get("SUPABASE_MODAL_STORAGE_SECRET_NAME", "supabase-s3")

# Modal setup
image = modal.Image.debian_slim(python_version="3.10").uv_pip_install(
    "chatterbox-tts==0.1.6",
    "fastapi[standard]==0.124.4",
    "peft==0.18.0",
    "boto3==1.40.39",
)
app = modal.App("chatterbox-tts", image=image)

with image.imports():
    import io
    import os
    import boto3
    from botocore.config import Config

    import torchaudio as ta
    from chatterbox.tts_turbo import ChatterboxTurboTTS
    from fastapi import (
        Depends,
        FastAPI,
        HTTPException,
        Security,
    )
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import StreamingResponse
    from fastapi.security import APIKeyHeader
    from pydantic import BaseModel, Field

    api_key_scheme = APIKeyHeader(
        name="x-api-key",
        scheme_name="ApiKeyAuth",
        auto_error=False,
    )

    def verify_api_key(x_api_key: str | None = Security(api_key_scheme)):
        expected = os.environ.get("CHATTERBOX_API_KEY", "")
        if not expected or x_api_key != expected:
            raise HTTPException(status_code=403, detail="Invalid API key")
        return x_api_key

    class TTSRequest(BaseModel):
        """Request model for text-to-speech generation."""

        prompt: str = Field(..., min_length=1, max_length=5000)
        voice_key: str = Field(..., min_length=1, max_length=300)
        temperature: float = Field(default=0.8, ge=0.0, le=2.0)
        top_p: float = Field(default=0.95, ge=0.0, le=1.0)
        top_k: int = Field(default=1000, ge=1, le=10000)
        repetition_penalty: float = Field(default=1.2, ge=1.0, le=2.0)
        norm_loudness: bool = Field(default=True)


@app.cls(
    gpu="a10g",
    scaledown_window=60 * 5,
    secrets=[
        modal.Secret.from_name("hf-token"),
        modal.Secret.from_name("chatterbox-api-key"),
        modal.Secret.from_name(SUPABASE_S3_SECRET_NAME),
    ],
)
@modal.concurrent(max_inputs=10)
class Chatterbox:
    @modal.enter()
    def load_model(self):
        self.bucket_name = os.environ.get("SUPABASE_STORAGE_BUCKET", "")
        self.s3_endpoint = os.environ.get("SUPABASE_STORAGE_S3_ENDPOINT", "")
        self.s3_region = os.environ.get("SUPABASE_STORAGE_REGION", "ap-northeast-2")

        if not self.bucket_name:
            raise RuntimeError("SUPABASE_STORAGE_BUCKET is required")
        if not self.s3_endpoint:
            raise RuntimeError("SUPABASE_STORAGE_S3_ENDPOINT is required")

        self.model = ChatterboxTurboTTS.from_pretrained(device="cuda")
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=self.s3_endpoint,
            region_name=self.s3_region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def _download_voice_to_tmp(self, voice_key: str) -> str:
        if not voice_key or voice_key.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid voice key")
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            self.s3_client.download_file(self.bucket_name, voice_key, tmp_path)
            return tmp_path
        except Exception:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
            raise HTTPException(
                status_code=400,
                detail=f"Voice not found at '{voice_key}'",
            )

    @modal.asgi_app()
    def serve(self):
        web_app = FastAPI(
            title="Chatterbox TTS API",
            description="Text-to-speech with voice cloning",
            docs_url="/docs",
            dependencies=[Depends(verify_api_key)],
        )
        web_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @web_app.post("/generate", responses={200: {"content": {"audio/wav": {}}}})
        def generate_speech(request: TTSRequest):
            try:
                audio_bytes = self.generate.local(
                    request.prompt,
                    request.voice_key,
                    request.temperature,
                    request.top_p,
                    request.top_k,
                    request.repetition_penalty,
                    request.norm_loudness,
                )
                return StreamingResponse(
                    io.BytesIO(audio_bytes),
                    media_type="audio/wav",
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to generate audio: {e}",
                )

        return web_app

    @modal.method()
    def generate(
        self,
        prompt: str,
        voice_key: str,
        temperature: float = 0.8,
        top_p: float = 0.95,
        top_k: int = 1000,
        repetition_penalty: float = 1.2,
        norm_loudness: bool = True,
    ):
        audio_prompt_path = self._download_voice_to_tmp(voice_key)
        wav = self.model.generate(
            prompt,
            audio_prompt_path=audio_prompt_path,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            repetition_penalty=repetition_penalty,
            norm_loudness=norm_loudness,
        )

        buffer = io.BytesIO()
        ta.save(buffer, wav, self.model.sr, format="wav")
        buffer.seek(0)
        try:
            return buffer.read()
        finally:
            try:
                os.remove(audio_prompt_path)
            except OSError:
                pass


@app.local_entrypoint()
def test(
    prompt: str = "Chatterbox running on Modal [chuckle].",
    voice_key: str = "voices/system/default.wav",
    output_path: str = "/tmp/chatterbox-tts/output.wav",
    temperature: float = 0.8,
    top_p: float = 0.95,
    top_k: int = 1000,
    repetition_penalty: float = 1.2,
    norm_loudness: bool = True,
):
    import pathlib

    chatterbox = Chatterbox()
    audio_bytes = chatterbox.generate.remote(
        prompt=prompt,
        voice_key=voice_key,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        repetition_penalty=repetition_penalty,
        norm_loudness=norm_loudness,
    )

    output_file = pathlib.Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_bytes(audio_bytes)
    print(f"Audio saved to {output_file}")
