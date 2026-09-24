from __future__ import annotations
import json, os
from pathlib import Path
from typing import Any

BACKEND_FILESYSTEM="filesystem"; BACKEND_CLOUD="cloud"
class StorageUnavailable(RuntimeError): pass

def storage_backend():
    raw=os.environ.get("SIS_STORAGE_BACKEND","").strip().lower()
    if not raw:return BACKEND_FILESYSTEM
    if raw not in {BACKEND_FILESYSTEM,BACKEND_CLOUD}:raise StorageUnavailable(f"UNSUPPORTED_STORAGE_BACKEND:{raw}")
    return raw

def _cloud_config():
    cfg={
      "endpoint":os.environ.get("SIS_CLOUD_STORAGE_URL","").strip(),
      "access":os.environ.get("SIS_CLOUD_STORAGE_ACCESS_KEY","").strip(),
      "secret":os.environ.get("SIS_CLOUD_STORAGE_SECRET_KEY","").strip(),
      "bucket":os.environ.get("SIS_CLOUD_STORAGE_BUCKET","").strip(),
      "region":os.environ.get("SIS_CLOUD_STORAGE_REGION","auto").strip() or "auto",
      "prefix":os.environ.get("SIS_CLOUD_STORAGE_PREFIX","sis").strip().strip("/")}
    missing=[k for k in ("endpoint","access","secret","bucket") if not cfg[k]]
    if missing:raise StorageUnavailable("CLOUD_STORAGE_NOT_CONFIGURED:"+",".join(missing))
    return cfg

def ensure_backend_ready():
    if storage_backend()==BACKEND_CLOUD:_cloud_config()

class JsonStore:
    def __init__(self,root:str|Path):
        ensure_backend_ready(); self.backend=storage_backend(); self.root=Path(root)
        self.cloud=_cloud_config() if self.backend==BACKEND_CLOUD else None; self._client=None

    @staticmethod
    def _validate(namespace,key):
        if not namespace or "/" in namespace or "\\" in namespace or ".." in namespace:raise ValueError("INVALID_STORAGE_NAMESPACE")
        if not key or "/" in key or "\\" in key or ".." in key:raise ValueError("INVALID_STORAGE_KEY")

    def _path(self,namespace,key):
        self._validate(namespace,key); p=self.root/namespace/f"{key}.json"; p.parent.mkdir(parents=True,exist_ok=True); return p

    def _object_key(self,namespace,key):
        self._validate(namespace,key); return "/".join(x for x in (self.cloud["prefix"],namespace,f"{key}.json") if x)

    def _prefix(self,namespace):
        self._validate(namespace,"probe"); parts=[x for x in (self.cloud["prefix"],namespace) if x]; return "/".join(parts)+"/"

    def _cloud_client(self):
        if self._client is not None:return self._client
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:raise StorageUnavailable("CLOUD_STORAGE_DEPENDENCY_MISSING") from e
        try:
            self._client=boto3.client("s3",endpoint_url=self.cloud["endpoint"],aws_access_key_id=self.cloud["access"],aws_secret_access_key=self.cloud["secret"],region_name=self.cloud["region"],config=Config(signature_version="s3v4"))
            return self._client
        except Exception as e:raise StorageUnavailable("CLOUD_STORAGE_CLIENT_INIT_FAILED") from e

    def put(self,namespace,key,payload:dict[str,Any],*,overwrite=True):
        if self.backend==BACKEND_FILESYSTEM:
            p=self._path(namespace,key)
            if p.exists() and not overwrite:raise FileExistsError(str(p))
            tmp=p.with_suffix(p.suffix+".tmp"); tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); os.replace(tmp,p); return
        object_key=self._object_key(namespace,key)
        if not overwrite and self.exists(namespace,key):raise FileExistsError(object_key)
        try:self._cloud_client().put_object(Bucket=self.cloud["bucket"],Key=object_key,Body=json.dumps(payload,ensure_ascii=False,indent=2).encode(),ContentType="application/json; charset=utf-8")
        except Exception as e:raise StorageUnavailable("CLOUD_STORAGE_PUT_FAILED") from e

    def get(self,namespace,key):
        if self.backend==BACKEND_FILESYSTEM:return json.loads(self._path(namespace,key).read_text(encoding="utf-8"))
        try:
            r=self._cloud_client().get_object(Bucket=self.cloud["bucket"],Key=self._object_key(namespace,key))
            return json.loads(r["Body"].read().decode("utf-8"))
        except Exception as e:raise StorageUnavailable("CLOUD_STORAGE_GET_FAILED") from e

    def exists(self,namespace,key):
        if self.backend==BACKEND_FILESYSTEM:return self._path(namespace,key).is_file()
        try:self._cloud_client().head_object(Bucket=self.cloud["bucket"],Key=self._object_key(namespace,key)); return True
        except Exception as e:
            response=getattr(e,"response",{}) or {}; status=(response.get("ResponseMetadata") or {}).get("HTTPStatusCode"); code=str((response.get("Error") or {}).get("Code",""))
            if status==404 or code in {"404","NoSuchKey","NotFound"}:return False
            raise StorageUnavailable("CLOUD_STORAGE_EXISTS_FAILED") from e

    def list(self,namespace):
        if self.backend==BACKEND_FILESYSTEM:
            root=self.root/namespace
            if not root.exists():return []
            out=[]
            for p in sorted(root.glob("*.json"),reverse=True):
                try:out.append(json.loads(p.read_text(encoding="utf-8")))
                except Exception:continue
            return out
        client=self._cloud_client(); keys=[]; token=None
        try:
            while True:
                kw={"Bucket":self.cloud["bucket"],"Prefix":self._prefix(namespace)}
                if token:kw["ContinuationToken"]=token
                r=client.list_objects_v2(**kw); keys += [x["Key"] for x in r.get("Contents",[]) if x.get("Key","").endswith(".json")]
                if not r.get("IsTruncated"):break
                token=r.get("NextContinuationToken")
                if not token:raise StorageUnavailable("CLOUD_STORAGE_LIST_PAGINATION_INVALID")
        except StorageUnavailable:raise
        except Exception as e:raise StorageUnavailable("CLOUD_STORAGE_LIST_FAILED") from e
        out=[]
        for object_key in sorted(keys,reverse=True):
            try:
                r=client.get_object(Bucket=self.cloud["bucket"],Key=object_key); out.append(json.loads(r["Body"].read().decode("utf-8")))
            except Exception as e:raise StorageUnavailable("CLOUD_STORAGE_LIST_READ_FAILED") from e
        return out
