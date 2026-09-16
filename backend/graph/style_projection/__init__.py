"""本棚投影スタイル分析システム。

参加者ごとの「本の配置・グルーピング・コメント」をNeo4jに構造化して保存し、
- 参加者ごとの投影スタイルを内容に依存しない構造指標として定量化する（metrics.py）
- 参加者間（閲覧者/所有者）の差分を後段のLLM翻訳に渡せる形で計算する（diff.py）

ためのモジュール群。

設計上の注意:
  graph.main_kg.neo4j_crud（既存の意味づけナレッジグラフ、Book/Concept/Impression系）
  とはノードラベルの大半（Work / ShelvedBook / Group / Comment / StyleProfile）が
  独立したスキーマだが、:Participant だけは両システムで共有する単一ノードである。
  以前はこちら側だけ participant_id（snake_case）を使っており、既存グラフ側の
  participantId（camelCase）と食い違って同じ参加者のParticipantノードが2重に
  できてしまっていた。現在は participantId（camelCase）に統一済み。

  構造指標（metrics.py）は Group.name や Comment.text などの意味データを
  一切読まない。読むのは投入（ingest.py）と、意味データそのものを返す
  参照クエリ（queries.py）だけに限定すること。
"""
