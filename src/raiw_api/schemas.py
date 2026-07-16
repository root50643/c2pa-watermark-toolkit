from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str = Field(description="穩定、可供程式判斷的錯誤碼。")
    message: str = Field(description="適合顯示或記錄的錯誤摘要。")
    details: Any = Field(default=None, description="選填的結構化驗證或診斷資訊；不包含 API Key 等秘密。")
    request_id: str = Field(description="本次 HTTP 請求的追蹤 ID，亦會出現在 X-Request-ID 回應標頭。")


class ErrorResponse(BaseModel):
    error: ErrorBody = Field(description="統一錯誤內容。")


class MeResponse(BaseModel):
    customer_id: str = Field(description="目前認證或匿名身分對應客戶的內部 ID。")
    customer_name: str = Field(description="目前客戶或匿名身分的顯示名稱。")
    external_id: str | None = Field(description="部署者設定的外部客戶編號；未設定時為 null。")
    key_id: str | None = Field(
        description="本次認證所用金鑰的內部 ID；停用 API Key 驗證並以匿名身分呼叫時為 null。"
    )
    key_prefix: str | None = Field(
        description="金鑰的非秘密前綴；停用 API Key 驗證並以匿名身分呼叫時為 null。"
    )


class IdentifyResponse(BaseModel):
    request_id: str = Field(description="本次 HTTP 請求的追蹤 ID。")
    archive_id: str = Field(description="處理紀錄 ID；目前與 request_id 相同。")
    report: dict[str, Any] = Field(
        description="上游辨識報告，包含格式、尺寸、AI provenance、可見及不可見浮水印訊號。"
    )


class JobAccepted(BaseModel):
    job_id: str = Field(description="GPU 非同步工作的唯一 ID。")
    archive_id: str = Field(description="此工作的處理紀錄 ID。")
    status: Literal["queued"] = Field(default="queued", description="接受工作時固定為 queued。")
    status_url: str = Field(
        description="輪詢工作狀態與進度的 URL；預設需相同客戶的 API Key，無 Key 模式則不帶金鑰。"
    )
    result_url: str = Field(description="結果下載 URL；工作成功前呼叫會回傳 409。")


class JobStatus(BaseModel):
    job_id: str = Field(description="GPU 非同步工作的唯一 ID。")
    archive_id: str = Field(description="此工作的處理紀錄 ID。")
    task_name: str = Field(description="工作流程名稱，目前為 invisible 或 all。")
    status: Literal["queued", "running", "succeeded", "failed"] = Field(description="目前工作狀態。")
    progress: int = Field(ge=0, le=100, description="伺服器估算的完成百分比；不是精確剩餘時間。")
    message: str | None = Field(default=None, description="目前階段或完成訊息；沒有訊息時為 null。")
    error: dict[str, Any] | None = Field(default=None, description="失敗時的錯誤碼與訊息；其他狀態為 null。")
    created_at: str = Field(description="工作建立時間，UTC ISO 8601 字串。")
    updated_at: str = Field(description="工作最後更新時間，UTC ISO 8601 字串。")
    result_url: str | None = Field(default=None, description="成功後的下載 URL；尚未成功時為 null。")


class CapabilitiesResponse(BaseModel):
    app_version: str = Field(description="目前 API 應用程式版本。")
    upstream_version: str = Field(description="固定使用的 remove-ai-watermarks 上游版本。")
    api_key_required: bool = Field(
        description="目前部署是否強制要求 X-API-Key；false 表示未帶金鑰時會使用匿名身分。"
    )
    supported_formats: list[str] = Field(description="伺服器接受的圖片副檔名（不含句點）。")
    max_upload_mb: int = Field(description="單一上傳檔案的大小上限，單位為 MiB。")
    max_image_pixels: int = Field(description="圖片解碼後的寬乘高像素上限。")
    archive_ready: bool = Field(description="Archive 儲存與 SQLite 是否可用。")
    redis_ready: bool = Field(description="Redis GPU queue 是否可連線；false 時 GPU 工作端點回傳 503。")
    visible_backends: list[str] = Field(description="可在可見移除與區域修補選用的 backend 名稱。")
    gpu_pipelines: list[str] = Field(description="GPU 不可見浮水印重生成可選用的 pipeline 名稱。")
