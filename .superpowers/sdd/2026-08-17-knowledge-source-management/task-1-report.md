# Task 1 Report: Knowledge Source Contract and Management Service

## Delivered

- Added the unified knowledge-source schema for `KOD_FOLDER` and `LOCAL_UPLOAD` libraries, local-upload ACLs, controlled upload binary storage, and `library_id` linkage into the existing `source -> document -> chunk -> embedding` chain.
- Kept KodCloud folders as stable IDs only. The schema does not store KodCloud paths, download URLs, browser sessions, or access tokens.
- Made the schema migration repeatable on an existing database: added fields use `IF NOT EXISTS`, the foreign-key existence check is scoped to `agent_knowledge_source`, and source-type/check constraints are replaced deterministically before being recreated.
- Added `AgentKnowledgeLibraryService` with tenant-scoped create/list/read/disable/sync-state operations, upload size and extension/MIME validation, and a dedicated `canReadLocalLibrary(tenantId, userId, libraryId)` authorization boundary.
- Local-upload ACL authorization accepts `ALL`, an explicitly listed user, or the current user’s direct `AdminUserDO.deptId`. It does not traverse a department tree or infer indirect department membership.
- Local library, binary payload, and ACL rows are created in one `agentEventTransactionManager` transaction with rollback for all exceptions.
- Registered and validated the `agent_knowledge_source_management_v1` deployment migration at startup.

## Tests

Passed:

```text
mvn -f yudao-server/pom.xml -Dtest=AgentKnowledgeLibraryServiceTest,AgentEventSchemaMigratorTest test
Tests run: 8, Failures: 0, Errors: 0, Skipped: 0
```

The test compile used `javac ... target 1.8`; the new service and tests avoid Java 9 collection factory APIs.

The plan’s root-reactor command remains blocked before compilation because the worktree does not contain the five Yudao aggregator module POMs:

```text
mvn -pl yudao-server -Dtest=AgentKnowledgeLibraryServiceTest test
Child module yudao-dependencies/yudao-framework/yudao-module-system/
yudao-module-infra/yudao-module-bpm pom.xml does not exist
```

Using `-f yudao-server/pom.xml` bypassed that incomplete aggregator and compiled all 57 server sources plus the relevant tests successfully.

## Residual Risk

- No disposable PostgreSQL instance with the deployment migration was available in this task, so migration reapplication was reviewed statically rather than executed twice against a live existing database. The service/test compile path is green.
