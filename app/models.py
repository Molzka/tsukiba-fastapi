from sqlalchemy import BigInteger, Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BoardOption(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    max_file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    bump_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    max_threads: Mapped[int] = mapped_column(Integer, nullable=False)
    max_message_length: Mapped[int] = mapped_column(Integer, nullable=False)
    captcha: Mapped[str] = mapped_column(String(32), nullable=False, default="simple")
    stop_board: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    post_id_seed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    parent: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, index=True
    )
    sage: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    time: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    file1: Mapped[str | None] = mapped_column(String(255))
    file1_info: Mapped[str | None] = mapped_column(String(255))
    file2: Mapped[str | None] = mapped_column(String(255))
    file2_info: Mapped[str | None] = mapped_column(String(255))
    file3: Mapped[str | None] = mapped_column(String(255))
    file3_info: Mapped[str | None] = mapped_column(String(255))
    file4: Mapped[str | None] = mapped_column(String(255))
    file4_info: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    status_time: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    verify: Mapped[str | None] = mapped_column(String(255), index=True)


Index("idx_posts_parent_status", Post.parent, Post.status)
