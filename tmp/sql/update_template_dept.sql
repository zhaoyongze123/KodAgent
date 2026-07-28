START TRANSACTION;
INSERT INTO system_dept (id,name,parent_id,sort,leader_user_id,status,creator,updater,tenant_id) VALUES
(300,'钱爱梅',201,1,216,0,'1','1',0),
(301,'邴燕萍',201,2,218,0,'1','1',0),
(302,'马倩',201,3,217,0,'1','1',0),
(303,'张华',201,4,219,0,'1','1',0)
ON DUPLICATE KEY UPDATE name=VALUES(name),parent_id=VALUES(parent_id),sort=VALUES(sort),leader_user_id=VALUES(leader_user_id),status=VALUES(status),deleted=0;
UPDATE system_dept SET parent_id=302,leader_user_id=217 WHERE id=202;
UPDATE system_dept SET parent_id=300,leader_user_id=221 WHERE id=203;
UPDATE system_dept SET parent_id=300,leader_user_id=218 WHERE id=204;
UPDATE system_dept SET parent_id=300,leader_user_id=222 WHERE id=205;
UPDATE system_dept SET name='综合科（行政/财务）',parent_id=301,leader_user_id=NULL WHERE id=206;
UPDATE system_dept SET parent_id=302,leader_user_id=224 WHERE id=207;
UPDATE system_dept SET name='数字城市规划所',parent_id=302,leader_user_id=217 WHERE id=208;
UPDATE system_dept SET parent_id=303,leader_user_id=225 WHERE id=209;
UPDATE system_dept SET parent_id=303,leader_user_id=NULL WHERE id=210;
UPDATE system_dept SET name='综合科（计划经营）',parent_id=303,leader_user_id=NULL WHERE id=211;
INSERT INTO system_dept (id,name,parent_id,sort,leader_user_id,status,creator,updater,tenant_id) VALUES
(315,'行政办公',206,1,223,0,'1','1',0),
(316,'财务管理',206,2,223,0,'1','1',0),
(317,'计划经营',211,1,227,0,'1','1',0)
ON DUPLICATE KEY UPDATE name=VALUES(name),parent_id=VALUES(parent_id),sort=VALUES(sort),leader_user_id=VALUES(leader_user_id),status=VALUES(status),deleted=0;
UPDATE system_users SET dept_id=300 WHERE id=216;
UPDATE system_users SET dept_id=301 WHERE id=218;
UPDATE system_users SET dept_id=302 WHERE id=217;
UPDATE system_users SET dept_id=303 WHERE id=219;
UPDATE system_users SET dept_id=315 WHERE id=223;
UPDATE system_users SET dept_id=317 WHERE id IN (227,228);
UPDATE system_users SET dept_id=210 WHERE id=230;

UPDATE bpm_process_definition_info p
JOIN bpm_approval_template t ON t.process_definition_id=p.process_definition_id
SET p.simple_model=REPLACE(
  REPLACE(
    REPLACE(
      p.simple_model,
      '"name":"默认部门负责人后院长"',
      '"name":"默认部门负责人及分管负责人后院长"'),
    '"showText":"其它人员：部门负责人后到院长"',
    '"showText":"其它人员：部门负责人→分管负责人→院长"'),
  '"name":"部门负责人审批"',
  '"name":"部门负责人及分管负责人审批"')
WHERE t.deleted=0 AND t.code LIKE 'tpl:oa_%' AND p.deleted=0;
UPDATE bpm_process_definition_info p
JOIN bpm_approval_template t ON t.process_definition_id=p.process_definition_id
SET p.simple_model=REPLACE(
  REPLACE(p.simple_model,'"candidateStrategy":37','"candidateStrategy":38'),
  '"candidateParam":"1"','"candidateParam":"2"')
WHERE t.deleted=0 AND t.code LIKE 'tpl:oa_%' AND p.deleted=0;

UPDATE ACT_GE_BYTEARRAY b
JOIN ACT_RE_MODEL m ON m.EDITOR_SOURCE_EXTRA_VALUE_ID_=b.ID_
SET b.BYTES_=REPLACE(
  REPLACE(
    REPLACE(
      REPLACE(b.BYTES_,'"name":"默认部门负责人后院长"','"name":"默认部门负责人及分管负责人后院长"'),
      '"showText":"其它人员：部门负责人后到院长"','"showText":"其它人员：部门负责人→分管负责人→院长"'),
    '"name":"部门负责人审批"','"name":"部门负责人及分管负责人审批"'),
  '"candidateStrategy":37','"candidateStrategy":38')
WHERE b.NAME_='source-extra' AND m.KEY_ LIKE 'oa_%';
UPDATE ACT_GE_BYTEARRAY b
JOIN ACT_RE_MODEL m ON m.EDITOR_SOURCE_EXTRA_VALUE_ID_=b.ID_
SET b.BYTES_=REPLACE(b.BYTES_,'"candidateParam":"1"','"candidateParam":"2"')
WHERE b.NAME_='source-extra' AND m.KEY_ LIKE 'oa_%';

UPDATE ACT_GE_BYTEARRAY b
JOIN ACT_RE_PROCDEF pd ON pd.DEPLOYMENT_ID_=b.DEPLOYMENT_ID_
JOIN bpm_approval_template t ON t.process_definition_id=pd.ID_
SET b.BYTES_=REPLACE(
  REPLACE(
    REPLACE(b.BYTES_,
      '<flowable:candidateStrategy xmlns:flowable="http://flowable.org/bpmn"><![CDATA[37]]></flowable:candidateStrategy>',
      '<flowable:candidateStrategy xmlns:flowable="http://flowable.org/bpmn"><![CDATA[38]]></flowable:candidateStrategy>'),
    '<flowable:candidateParam xmlns:flowable="http://flowable.org/bpmn"><![CDATA[1]]></flowable:candidateParam>',
    '<flowable:candidateParam xmlns:flowable="http://flowable.org/bpmn"><![CDATA[2]]></flowable:candidateParam>'),
  'name="部门负责人审批"','name="部门负责人及分管负责人审批"')
WHERE b.NAME_ LIKE '%.bpmn' AND t.deleted=0 AND t.code LIKE 'tpl:oa_%' AND pd.SUSPENSION_STATE_=1;
COMMIT;
