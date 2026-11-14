from sqlalchemy import create_engine, String, Column, Integer, Float, Date, ForeignKey, func
from sqlalchemy.orm import Session, declarative_base
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# ---------- Database connection ----------
ph = PasswordHasher()

DB_URL = "sqlite:///warehouse.db"
engine = create_engine(DB_URL)

USERNAME = "Rohith"
PASSWORD = "123456"

ACCESS_TOKEN_EXPIRY = 15 #mins
REFRESH_TOKEN_EXPIRY = 7 * 24 * 60
SECRET_KEY = "SECRET123"
ALGORITHM = "HS256"

# ---------- Tables / Models ----------

Base = declarative_base()


class DispatchBatch(Base):
    __tablename__ = "dispatch_batches"

    id = Column(Integer, primary_key=True)
    destination = Column(String)
    vehicle = Column(String)
    status = Column(String)          # planned / dispatched
    dispatch_date = Column(Date)


class Package(Base):
    __tablename__ = "packages"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    destination = Column(String)
    weight = Column(Float)
    arrival_date = Column(Date)
    status = Column(String)          # received / ready / dispatched
    batch_id = Column(Integer, ForeignKey("dispatch_batches.id"), nullable=True)

class User(Base):
    __tablename__ = "Users"

    user_id = Column(Integer, primary_key=True)
    user_name = Column(String)
    password = Column(String)

# Create the tables if they don't exist.
Base.metadata.create_all(engine)


def package_to_dict(p):
    return {
        "id": p.id,
        "name": p.name,
        "destination": p.destination,
        "weight": p.weight,
        "arrival_date": p.arrival_date,
        "status": p.status,
        "batch_id": p.batch_id
    }


def batch_to_dict(b, package_count):
    return {
        "id": b.id,
        "destination": b.destination,
        "vehicle": b.vehicle,
        "status": b.status,
        "dispatch_date": b.dispatch_date,
        "package_count": package_count
    }


# ---------- PACKAGES: CREATE ----------

def create_package(name, destination, weight, arrival_date, status, batch_id=None):
    session = Session(engine)

    package = Package(
        name=name,
        destination=destination,
        weight=weight,
        arrival_date=arrival_date,
        status=status,
        batch_id=batch_id
    )

    session.add(package)
    session.commit()
    session.refresh(package)

    result = package_to_dict(package)

    session.close()
    return result


# ---------- PACKAGES: READ (search + filter) ----------

def get_packages(destination=None, status=None, arrival_date=None):
    session = Session(engine)

    query = session.query(Package)

    if destination is not None:
        query = query.filter(Package.destination.ilike(destination))
    if status is not None:
        query = query.filter(Package.status == status)
    if arrival_date is not None:
        query = query.filter(Package.arrival_date == arrival_date)

    result = []

    for package in query.order_by(Package.id).all():
        result.append(package_to_dict(package))

    session.close()
    return result


# ---------- PACKAGES: READ ONE ----------

def get_package(package_id):
    session = Session(engine)

    package = session.get(Package, package_id)

    if package is None:
        session.close()
        return None

    result = package_to_dict(package)

    session.close()
    return result


# ---------- PACKAGES: UPDATE (partial) ----------

def update_package(package_id, changes):
    """changes = dict with only the fields to update."""
    session = Session(engine)

    package = session.get(Package, package_id)

    if package is None:
        session.close()
        return None

    for field, value in changes.items():
        setattr(package, field, value)

    session.commit()

    result = package_to_dict(package)

    session.close()
    return result


# ---------- PACKAGES: DELETE ----------

def delete_package(package_id):
    session = Session(engine)

    package = session.get(Package, package_id)

    if package is None:
        session.close()
        return False

    session.delete(package)
    session.commit()

    session.close()
    return True


# ---------- DISPATCH BATCHES ----------

def get_batch(batch_id):
    session = Session(engine)

    batch = session.get(DispatchBatch, batch_id)

    session.close()
    return batch is not None


def get_dispatch_batches(destination=None, vehicle=None, status=None):
    session = Session(engine)

    query = session.query(DispatchBatch, func.count(Package.id)) \
        .outerjoin(Package, Package.batch_id == DispatchBatch.id) \
        .group_by(DispatchBatch.id)

    if destination is not None:
        query = query.filter(DispatchBatch.destination.ilike(destination))
    if vehicle is not None:
        query = query.filter(DispatchBatch.vehicle.ilike(vehicle))
    if status is not None:
        query = query.filter(DispatchBatch.status == status)

    result = []

    for batch, package_count in query.order_by(DispatchBatch.id).all():
        result.append(batch_to_dict(batch, package_count))

    session.close()
    return result


# ---------- ANALYTICS ----------

def get_dispatch_summary():
    session = Session(engine)

    total = session.query(Package).count()
    dispatched = session.query(Package).filter(Package.status == "dispatched").count()

    rows = session.query(Package.destination, func.count(Package.id)) \
        .group_by(Package.destination).all()

    destination_counts = {}
    for destination, count in rows:
        destination_counts[destination] = count

    session.close()
    return {
        "total_packages_received": total,
        "total_pending_dispatch": total - dispatched,
        "total_dispatched": dispatched,
        "destination_wise_count": destination_counts
    }

def verify_login(username, password):
    session = Session(engine)
    user = session.query(User).filter_by(user_name = username).first()
    if user is None:
        session.close()
        return False
    try:
        ph.verify(user.password, password)
    except VerifyMismatchError:
        session.close()
        return False
    session.close()
    access_token = create_token(username=username, token_type="access")
    refresh_token = create_token(username=username, token_type="refresh")
    return {"access_token": access_token, "refresh_token": refresh_token}

def create_token(username, token_type):
    time = ACCESS_TOKEN_EXPIRY
    if token_type == "refresh":
        time = REFRESH_TOKEN_EXPIRY
    payload = {
        "username": username,
        "token_type": token_type,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=time)
    }
    token = jwt.encode(payload=payload, key=SECRET_KEY, algorithm=ALGORITHM)
    return token

def verify_token(token, token_type):
    try:
        payload = jwt.decode(jwt=token, key=SECRET_KEY,algorithms=[ALGORITHM])
    except:
        return False

    if payload["token_type"] == token_type:
        return payload["username"]
    return False

# ------ Users ------
def register_user(user_name:str, password:str):
    session = Session(engine)
    user_exists = session.query(User).filter_by(user_name=user_name).first()

    if user_exists is not None:
        session.close()
        return False

    session.add(User(user_name=user_name,password=ph.hash(password)))
    session.commit()
    session.close()
    return True




# ---------- SEED (no batch-create endpoint in the PRD, so add a few batches) ----------

def seed_batches():
    session = Session(engine)

    if session.query(DispatchBatch).count() == 0:
        session.add_all([
            DispatchBatch(destination="Bangalore", vehicle="KA-01-AB-1234", status="planned"),
            DispatchBatch(destination="Chennai", vehicle="TN-09-CD-5678", status="planned"),
            DispatchBatch(destination="Mumbai", vehicle="MH-12-EF-9012", status="dispatched"),
        ])
        session.commit()

    session.close()


seed_batches()
