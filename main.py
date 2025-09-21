from typing import List, Optional
import uuid
import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from sqlmodel import Session, SQLModel, Field, Relationship, create_engine, select

# --- データベース設定 ---
DATABASE_URL = "sqlite:///database.db"
engine = create_engine(DATABASE_URL, echo=True)

# --- モデル定義 (修正済み) ---
class Task(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str
    description: str | None = None
    is_completed: bool = False
    due_date: datetime.date | None = None
    
    owner_id: uuid.UUID = Field(foreign_key="user.id")
    owner: "User" = Relationship(back_populates="tasks")

class User(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    username: str = Field(index=True, unique=True)
    hashed_password: str = Field()
    
    tasks: List["Task"] = Relationship(back_populates="owner")

# --- APIスキーマ (データモデル) ---
class TaskCreate(SQLModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime.date] = None

class TaskUpdate(SQLModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_completed: Optional[bool] = None
    due_date: Optional[datetime.date] = None

class UserCreate(SQLModel):
    username: str
    password: str

class UserRead(SQLModel):
    id: uuid.UUID
    username: str

class UserReadWithTasks(UserRead):
    tasks: List[Task] = []

# --- DBセッション管理 ---
def get_session():
    with Session(engine) as session:
        yield session

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield
    print("INFO:     Application shutdown.")

app = FastAPI(lifespan=lifespan)

# --- 認証（ダミー） ---
async def get_current_user(session: Session = Depends(get_session)) -> User:
    user = session.exec(select(User)).first()
    if not user:
        raise HTTPException(status_code=404, detail="No users found. Please create a user first.")
    return user

# --- APIエンドポイント ---
@app.post("/users/", response_model=UserRead)
def create_user(user_create: UserCreate, session: Session = Depends(get_session)):
    db_user = User.model_validate(user_create, update={"hashed_password": user_create.password + "notreallyhashed"})
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

@app.get("/users/", response_model=List[UserReadWithTasks])
def read_users(session: Session = Depends(get_session)):
    users = session.exec(select(User)).all()
    return users

@app.post("/tasks/", response_model=Task)
async def create_task(
    task: TaskCreate, 
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    task_data = task.model_dump()
    update_data = {"owner_id": current_user.id} # ownerの代わりにowner_idを直接指定
    db_task = Task.model_validate({**task_data, **update_data})
    
    session.add(db_task)
    session.commit()
    session.refresh(db_task)
    return db_task

@app.get("/tasks/", response_model=List[Task])
def read_tasks(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    tasks = session.exec(
        select(Task).where(Task.owner_id == current_user.id)
    ).all()
    return tasks

# (GET by id, PATCH, DELETEのエンドポイントは、所有者チェックを追加するとさらに良くなりますが、
#  まずはここまででStep 3の主目的は達成です)