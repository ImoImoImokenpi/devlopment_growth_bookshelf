"""
SQLite と Neo4j のレコード数・リレーション数を確認するスクリプト。
プロジェクトルートから実行:
  python backend/scripts/check_relations.py
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from admin_neo4j.neo4j_driver import get_session

conn = sqlite3.connect(Path(__file__).parent.parent / "bookshelf.db")
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM registered_books")
print("SQLite registered_books:", cur.fetchone()[0], "冊")
cur.execute("SELECT COUNT(*) FROM shelflayout")
print("SQLite shelflayout (棚に配置済み):", cur.fetchone()[0], "冊")
cur.execute("SELECT COUNT(*) FROM myhand")
print("SQLite myhand (手持ち):", cur.fetchone()[0], "冊")
conn.close()

with get_session() as session:
    r = session.run("MATCH (b:Book) RETURN count(b) AS n")
    print("\nNeo4j Book ノード:", r.single()["n"])
    r = session.run("MATCH (a:Author) RETURN count(a) AS n")
    print("Neo4j Author ノード:", r.single()["n"])
    r = session.run("MATCH ()-[:WRITTEN_BY]->() RETURN count(*) AS n")
    print("Neo4j WRITTEN_BY リレーション:", r.single()["n"])
    r = session.run("MATCH (p:Publisher) RETURN count(p) AS n")
    print("Neo4j Publisher ノード:", r.single()["n"])
    r = session.run("MATCH ()-[:PUBLISHED_BY]->() RETURN count(*) AS n")
    print("Neo4j PUBLISHED_BY リレーション:", r.single()["n"])

    # WRITTEN_BY を持つ Book だけ数える
    r = session.run("MATCH (b:Book)-[:WRITTEN_BY]->() RETURN count(DISTINCT b) AS n")
    print("\nWRITTEN_BY を持つ Book:", r.single()["n"])
    r = session.run("MATCH (b:Book)-[:PUBLISHED_BY]->() RETURN count(DISTINCT b) AS n")
    print("PUBLISHED_BY を持つ Book:", r.single()["n"])

    # 著者を共有している本のペア数
    r = session.run("""
        MATCH (b1:Book)-[:WRITTEN_BY]->(a:Author)<-[:WRITTEN_BY]-(b2:Book)
        WHERE b1 <> b2
        RETURN count(DISTINCT b1) AS n
    """)
    print("\n同著者の本と繋がっている Book:", r.single()["n"])
