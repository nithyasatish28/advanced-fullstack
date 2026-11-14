from datetime import date
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import functions

app = FastAPI(title="Warehouse Dispatch Management System")

STATUSES = ["received", "ready", "dispatched"]


# ---------- Request bodies (Pydantic) ----------
class PackageCreate(BaseModel):
    name: str
    destination: str
    weight: float
    arrival_date: date
    status: str = "received"
    batch_id: int = None


class PackageUpdate(BaseModel):
    name: str = None
    destination: str = None
    weight: float = None
    arrival_date: date = None
    status: str = None
    batch_id: int = None


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    user_name: str
    password: str


def check_token(token):
    username = functions.verify_token(token=token, token_type="access")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or Expired token")
    return username


def validate_package(weight=None, status=None, batch_id=None):
    if weight is not None and weight <= 0:
        raise HTTPException(status_code=422, detail="Weight must be greater than 0")
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=422, detail=f"Status must be one of {STATUSES}")
    if batch_id is not None and functions.get_batch(batch_id=batch_id) == False:
        raise HTTPException(status_code=404, detail="Dispatch batch not found")


@app.get("/")
def hello():
    return {"message": "Warehouse Dispatch API. Docs at /docs"}


# ---------- Packages ----------
@app.post("/packages", status_code=201)
def create_package(data: PackageCreate, token = Header(None)):
    check_token(token)
    validate_package(weight=data.weight, status=data.status, batch_id=data.batch_id)
    return functions.create_package(name=data.name, destination=data.destination, weight=data.weight,
                                    arrival_date=data.arrival_date, status=data.status, batch_id=data.batch_id)


@app.get("/packages")
def get_packages(destination=None, status=None, arrival_date: date = None, token = Header(None)):
    check_token(token)
    return functions.get_packages(destination=destination, status=status, arrival_date=arrival_date)


@app.get("/packages/{package_id}")
def get_package(package_id: int, token = Header(None)):
    check_token(token)
    package = functions.get_package(package_id=package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="Package not found")
    return package


@app.patch("/packages/{package_id}")
def update_package(package_id: int, data: PackageUpdate, token = Header(None)):
    check_token(token)
    if functions.get_package(package_id=package_id) is None:
        raise HTTPException(status_code=404, detail="Package not found")
    validate_package(weight=data.weight, status=data.status, batch_id=data.batch_id)

    changes = data.model_dump(exclude_none=True)  # keep only the fields that were sent

    if changes == {}:
        raise HTTPException(status_code=422, detail="Nothing to update")
    return functions.update_package(package_id=package_id, changes=changes)


@app.delete("/packages/{package_id}")
def delete_package(package_id: int, token = Header(None)):
    check_token(token)
    package = functions.get_package(package_id=package_id)
    if package is None:
        raise HTTPException(status_code=404, detail="Package not found")
    if package["status"] == "dispatched":
        raise HTTPException(status_code=400, detail="Dispatched packages cannot be deleted")
    functions.delete_package(package_id=package_id)
    return {"message": "Package deleted"}


# ---------- Dispatch ----------
@app.get("/dispatch-batches")
def get_dispatch_batches(destination=None, vehicle=None, status=None, token = Header(None)):
    check_token(token)
    return functions.get_dispatch_batches(destination=destination, vehicle=vehicle, status=status)


# ---------- Analytics ----------
@app.get("/analytics/dispatch-summary")
def dispatch_summary(token = Header(None)):
    check_token(token)
    return functions.get_dispatch_summary()


@app.post("/login")
def login(data: LoginRequest):
    token = functions.verify_login(username=data.username, password=data.password)
    if not token:
        raise HTTPException(status_code=401, detail="Invalid Credentials")
    return token

@app.post("/refresh")
def refresh(refresh_token = Header(None, convert_underscores=False)):
    username = functions.verify_token(token=refresh_token, token_type="refresh")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or Expired refresh token")

    access_token = functions.create_token(username=username, token_type="access")
    return {"access_token": access_token}

@app.post("/register")
def register_user(data: RegisterRequest):
    if functions.register_user(user_name=data.user_name, password=data.password):
        return {"message": "user registered successfully"}
    raise HTTPException(status_code=400, detail="User already exists")
