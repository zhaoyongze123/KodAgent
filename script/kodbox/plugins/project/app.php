<?php
/**
 * 项目看板;
 * 项目接口: projectInfo,projectLog,projectListSelf,projectListTemplate,
 * 项目操作: projectAdd,projectCopyCreate,projectImport,projectEdit,projectFavAdd,projectFavCancel,
 * 		projectArchive,projectArchiveCancel,projectRemove,projectRemoveCancel,projectRemoveForce,projectExit
 * 
 * 任务接口: taskProject,taskInfo,taskLog;//(列表默认不拉取desc; taskInfo才获取desc)
 * 任务操作: taskAdd,taskEdit,taskSetUser,taskSetMeta,taskSort,taskCopyTo,taskMoveTo,taskArchive,
 * 			taskArchiveCancel,taskRemove,taskRemoveCancel,taskRemoveForce
 * 			taskAddMutil,taskEditMutil,taskCopyMoveMutil
 * 
 * 管理员接口: adminInfo,adminList,adminLog,adminOption
 */
class projectPlugin extends PluginBase{
	function __construct(){
		parent::__construct();
		$this->loadModel();
	}
	public function regist(){
		$this->hookRegist(array(
			'user.commonJs.insert'	=> 'projectPlugin.echoJs',
			'comment.checkType'		=> 'projectPlugin.commentCheckType',
			'comment.checkAuth'		=> 'projectPlugin.commentCheckAuth',
			'comment.checkSelf'		=> 'projectPlugin.commentCheckSelf',
		));
	}
	public function echoJs(){
		if(!$this->isInstall()) return;
		$options = $this->getConfig();
		$assign  = array(
			"{{projectOption}}" => base64_encode(json_encode($options)),
		);
		$this->echoFile('static/main.js',$assign);
	}
	
	// 检测并创建数据表;
	private function checkInstall(){
		if($this->isInstall()) return;
		$tableHas = 'plugin_project';
		$tables = Model()->db()->getTables();
		if(in_array($tableHas, $tables)){return $this->installSet('1');}
		$sqlFile = $this->pluginPath.'lib/plugin_project.sql';
		if(stristr($this->config['database']['DB_TYPE'],'sqlite')){
			$sqlFile = $this->pluginPath.'lib/plugin_project_sqlit.sql';
		}
		$sqlArr = sqlSplit(file_get_contents($sqlFile));
		foreach($sqlArr as $sql){
			Model()->db()->execute($sql);
		}

		$tables = Model()->db()->getTables();
		if(in_array($tableHas,$tables)){$this->installSet('1');}
	}
	private function installSet($set){
		Model('SystemOption')->set('installDB',$set,'projectApp');
	}
	private function isInstall($set = false){
		return Model('SystemOption')->get('installDB','projectApp') == '1';
	}
	// 导出插件sql表前,创建sqlit兼容的结构; http://127.0.0.1/kod/kodbox/?plugin/project/test
	public function test(){
		$db = $this->config['database'];
		$sqlFile = $this->pluginPath.'lib/plugin_project.sql';
		$sqlFileSqlite = $this->pluginPath.'lib/plugin_project_sqlit.sql';
		@include_once(WEB_ROOT.'kod/doc/tools/mysql2sqlite/lib/sqlTools.class.php');
		sqlTools::toSqlite($db['DB_NAME'],$sqlFileSqlite,file_get_contents($sqlFile),false);
		pr('ok;db_type='.$db['DB_TYPE'].';sqlite='.intval(stristr($db['DB_TYPE'],'sqlite')));
	}
	// 禁用启用;启用时检测;
	public function onChangeStatus($status){
		$this->installSet('0');
		if($status == '1'){
			$this->checkInstall();
			$error = LNG('project.tips.installError');
			if(!$this->isInstall()){show_json($error,false);}
		}
	}
	
	
	public $model;
	public $modelData;
	public $modelLog;
	public $modelTask;
	public function loadModel(){
		if(strtolower(MOD) != 'plugin' || strtolower(ST)  != 'project') return;
		if(strtolower(ACT)  == 'echojs') return;
		$this->loadModelNow();
		// $this->checkInstall();
	}
	private function loadModelNow(){
		if($this->modelData) return;
		include($this->pluginPath.'lib/ProjectModel.class.php');
		include($this->pluginPath.'lib/ProjectModelFile.class.php');
		include($this->pluginPath.'lib/ProjectModelData.class.php');
		include($this->pluginPath.'lib/ProjectModelLog.class.php');
		include($this->pluginPath.'lib/ProjectModelTask.class.php');
		include($this->pluginPath.'lib/ProjectModelAdmin.class.php');
		include($this->pluginPath.'lib/ProjectModelSelf.class.php');
		include($this->pluginPath.'lib/ProjectModelGroup.class.php');
		include($this->pluginPath.'lib/ProjectAgentBridge.class.php');
		
		$this->options 		= $this->getConfig();
		$this->modelUser	= Model('plugin_project_user');
		$this->modelData 	= new ProjectModelData();
		$this->modelLog  	= new ProjectModelLog();
		$this->model 		= new ProjectModel($this);
		$this->modelTask 	= new ProjectModelTask($this);
		$this->modelAdmin 	= new ProjectModelAdmin($this);
		$this->modelSelf 	= new ProjectModelSelf($this);
		$this->modelGroup 	= new ProjectModelGroup($this);
		$this->modelGroupTemplate = new ProjectModelGroup($this,'projectTemplate');
		$this->isAdmin 		= $this->adminCheck(true);
		
		Hook::bind('project.taskAdd.after',array($this,'taskImageLink'));
		Hook::bind('project.taskEdit.after',array($this,'taskImageLink'));
		Hook::bind('project.taskRemove.after',array($this,'taskImageClear'));
	}

	/**
	 * Agent 只读桥接入口。
	 *
	 * 该入口不复用浏览器 Cookie，而是由 ProjectAgentBridge 校验 Java
	 * 签发的短期 HMAC 票据，再使用同一套项目/任务权限规则输出稳定 JSON。
	 */
	public function agent(){
		$bridge = new ProjectAgentBridge($this);
		$bridge->dispatch(strtolower((string)_get($this->in,'agentAction','projects')));
	}
	
	// -----------------------------项目列表-----------------------------------
	// 默认所有接口都传入projectID;(除了项目新建,项目列表等接口); 
	// 项目及属性修改,任务及属性修改: 默认都传入logID; 拉取最后更新的日志id;(用作diff处理)
	public function projectInfo(){
		$this->checkAuthShow();
		$this->showProject();
	}
	public function projectLog(){
		$this->checkAuthShow();
		$logList = $this->modelLog->listProject($this->in['projectID'],$this->logParamParse());
		show_json($logList,true,$this->logChange('task',false));
	}
	public function projectListSelf(){
		KodUser::checkLogin();
		//array(fav'=>array(),'self'=>array(),'archive'=>array(),'recycle'=>array());
		$listGroup = $this->modelGroup->listData();
		show_json($this->model->listDataSelf(),true,$listGroup);
	}
	
	// 模版列表;
	public function projectListTemplate(){
		$result = array(
			'listData'	=> $this->model->listTemplate(),
			'listGroup'	=> $this->modelGroupTemplate->listData(),
		);
		show_json($result,true);
	}
	
	public function taskListSelf(){
		KodUser::checkLogin();
		//array('task'=>array(),'project'=>array());
		show_json($this->modelSelf->taskListSelf(),true);
	}
	
	// 日志筛选条件解析处理;
	private function logParamParse(){
		$logMap = array(
			'project'		=> 'project.add,project.edit,project.metaSet,project.setUser,project.userExit'.
								',project.remove,project.archive,project.removeCancel,project.archiveCancel',
			'task.add'		=> 'task.add',
			'task.edit'		=> 'task.edit,task.setUser',
			'task.move'		=> 'task.setSort,task.moveIn,task.moveOut',
			'task.metaSet'	=> 'task.metaSet',
			'task.delete'	=> 'task.remove,task.archive,task.removeCancel,task.archiveCancel,task.removeForce',
			'comment.change'=> 'comment.add,comment.remove',
		);
		$data = Input::getArray(array(
			"userID"		=> array("check"=>"number",'default'=>''),
			"timeStart"		=> array("check"=>"number",'default'=>''),
			"timeTo"		=> array("check"=>"number",'default'=>''),
			"taskLogType"	=> array("check"=>"in",'default'=>'','param'=>array_keys($logMap)),
		));
		$where = array();
		if($data['userID']){$where['userID'] = $data['userID'];}
		if($data['timeStart']){$where['createTime'] = array('>=',$data['timeStart']);}
		if($data['timeTo']){$where['createTime'] = array('<=',$data['timeTo']);}
		if($data['timeStart'] && $data['timeTo']){
			$where['createTime'] = array('between',array($data['timeStart'],$data['timeTo']));
		}
		if($data['taskLogType']){
			$logType = explode(',', $logMap[$data['taskLogType']]);
			$where['logType'] = array('in',$logType);
		}
		return $where;
	}
	
	// -----------------------------项目操作-----------------------------------
	public function projectAdd(){
		KodUser::checkLogin();
		$this->checkAddProject();
		$data = Input::getArray(array(
			"name"		=> array("check"=>"require"),
			"desc"		=> array("check"=>"require",'default'=>''),
		));
		
		// 新建模版处理;
		$meta = json_decode(_get($this->in,'meta'),true);$metaOld = $meta;	
		if(_get($this->in,'isTemplate') == '1'){
			if(!$this->isAdmin){show_json(LNG('explorer.noPermissionAction'),false);}
			$data['status'] = ProjectModel::STATUS_TEMPLATE;
		}
		$projectID = $this->model->dataAdd($data);
		$this->projectUpdate($projectID,true);
		
		$meta = ProjectModelData::projectMeta($projectID,$this->options);
		$this->projectMetaSet($projectID,$meta,true);
		show_json($this->getProjectInfo($projectID),true);
	}
	public function projectCopyCreate(){
		KodUser::checkLogin();
		$this->checkAddProject();
		$data = Input::getArray(array(
			"projectFrom"	=> array("check"=>"number"),
			"name"			=> array("check"=>"require",'default'=>''),
			"desc"			=> array("check"=>"require",'default'=>''),
			"authType"		=> array("check"=>"require",'default'=>''),
			"isTemplate"	=> array("check"=>"number",'default'=>'0'),
			"options"		=> array("check"=>"require",'default'=>''),
		));
		if(_get($this->in,'isTemplate') == '1'){
			if(!$this->isAdmin){show_json(LNG('explorer.noPermissionAction'),false);}
		}
		
		$this->checkAuth('show',$data['projectFrom']);
		$projectID = $this->model->copyCreate($data);
		show_json($this->getProjectInfo($projectID),true);
	}
	
	// 通过外部项目模版导入(忽略用户;文件内容)
	public function projectImport(){
		KodUser::checkLogin();
		$this->checkAddProject();
		$data = Input::getArray(array(
			"taskList"		=> array("check"=>"json",'default'=>array()),
			"projectInfo"	=> array("check"=>"json",'default'=>array()),
		));
		if(empty($data['projectInfo']['name'])){
			$data['projectInfo']['name'] = LNG('project.meta.name');
		}
		if(empty($data['projectInfo']['metaInfo'])){
			$data['projectInfo']['metaInfo'] = array();
		}
		
		$projectID = $this->model->dataAdd($data['projectInfo']);
		$this->projectMetaSet($projectID,$data['projectInfo']['metaInfo'],true);
		$this->modelTask->dataAddMutilAndChild($data['taskList'],$projectID);
		show_json($this->getProjectInfo($projectID),true);
	}
	
	public function projectEdit(){
		$this->checkAuthAdmin();
		$data = Input::getArray(array(
			"name"		=> array("check"=>"require",'default'=>''),
			"desc"		=> array("check"=>"require",'default'=>''),
		));
		if(!isset($this->in['name'])){unset($data['name']);}
		if(!isset($this->in['desc'])){unset($data['desc']);}
		if($data){$this->model->dataEdit($this->in['projectID'],$data);}
		$this->projectUpdate($this->in['projectID']);
		$this->showProject();
	}
	private function projectUpdate($projectID,$isCreate = false){
		if(isset($this->in['meta']) && $this->in['meta']){
			$meta = $this->checkMetaData($this->in['meta'],$this->model->metaKeys);
			$this->projectMetaSet($projectID,$meta,$isCreate);
		}
		if(isset($this->in['userList']) && $this->in['userList']){
			$userList = json_decode($this->in['userList'],true);
			if(!$userList){show_json(LNG('project.tips.userEmpty'),false);}
			$this->model->dataSetUser($projectID,$userList,$isCreate);
		}
	}
	
	// 项目扩展属性设置, 对象数组时最小化变更(避免覆盖问题, 多人修改时全部覆盖为最后一个操作)
	private function projectMetaDiff($projectInfo,&$meta){
		if(!isset($this->in['metaDiff'])){return;}
		$diff = json_decode($this->in['metaDiff'],true);
		if(!$diff || !is_array($diff)){return;}

		$dataLike = array(// 对象数组,diff变更对比结构
			'tagList'		=> array(array('_idKey_'=>'id','_autoID_'=>"string")),
			'taskFinishDiy' => array(array('_idKey_'=>'id','_autoID_'=>"string")),
			'application'   => array(array('_idKey_'=>'id','_autoID_'=>"string")),
			'projectOption' => array(array('_idKey_'=>'id','_autoID_'=>"string")),
			'userField' 	=> array(array('_idKey_'=>'id','_autoID_'=>"string",
				'selectValues'=>array(array('_idKey_'=>'id','_autoID_'=>"string"))
			)),
		);
		$metaInfo = _get($projectInfo,'metaInfo',array());
		$metaJson = array();
		foreach($meta as $key => $value){
			if(!isset($dataLike[$key])){continue;}
			$metaJson[$key] = _get($metaInfo,$key,array());
		}
		$metaJsonTo = kodDiff::diffApply($metaJson,$diff,$dataLike);
		foreach($metaJsonTo as $key => $value){
			if(!$diff[$key]){
				unset($meta[$key]);unset($metaJson[$key]);
				continue;
			}
			kodDiff::arrayAutoID($value,'id','string');
			if(is_array($value) && $key == 'userField'){
				foreach($value as $i=>$item){
					$selects = $item['selectValues'];
					$selects = is_array($selects) ? $selects:json_decode($selects,true);
					kodDiff::arrayAutoID($selects,'id','string');
					$value[$i]['selectValues'] = $selects;
				}
			}
			$meta[$key] = $value;// 使用diff做最小化变更;
		}
		// trace_log([$metaJson,$metaJsonTo,$diff,$meta]);	
	}
	
	// 编辑项目meta数据; 模版情况处理;
	private function projectMetaSet($projectID,$meta,$isCreate){
		$projectInfo = $this->getProjectInfo($projectID);
		$this->projectMetaDiff($projectInfo,$meta);
		$metaOld = $meta;
		if(!$projectInfo){return;}
		if($this->model->isTemplate($projectInfo)){
			if(!$this->isAdmin){show_json(LNG('explorer.noPermissionAction'),false);}
			unset($meta['groupAt']);
			unset($this->in['userList']);
			$meta['templateType'] = 'template';
			if(!empty($meta['templateDesc'])){
				$meta['templateDesc'] = Html::clean($meta['templateDesc']);
				$desc = ModelBase::textEncode($meta['templateDesc']);
				if(strlen($desc) > 60000){$meta['templateDesc'] = '';}
			}
		}else{
			unset($meta['templateType']);
			unset($meta['templateDesc']);
			unset($meta['templateGroupAt']);
		}
		// trace_log([$metaOld,$meta]);
		$this->model->dataSetMeta($projectID,$meta,$isCreate);
	}	
	
	private function checkMetaData($metaStr,$allowKeys){
		$errorField  = LNG('common.unknow').' key [meta]!';
		$errorLength = LNG('common.lengthLimit').' [meta]!';
		$meta = json_decode($metaStr,true);
		foreach($meta as $key => $value){
			if(!in_array($key,$allowKeys)){show_json($errorField,false);}
			if(strlen(json_encode($value)) >= 60000){show_json($key.$errorLength,false);}
		}
		return $meta;
	}
	public function projectExit(){
		$this->checkAuthShow();
		$result = $this->model->projectExit($this->in['projectID']);
		$errorMap = array(
			'notInProject'	=> LNG('project.tips.notInProject'),
			'noAuthAdmin' 	=> LNG('project.tips.adminCanNotExit'),
		);
		$code = $result ? false:true;
		$errrorMsg = $errorMap[$result] ? $errorMap[$result]:false;
		show_json($code ? LNG('explorer.success'):$errrorMsg,$code);
	}
	private function projectAction($action,$checkAdmin=false){
		if($checkAdmin){$this->checkAuthAdmin();}
		if(!$checkAdmin){$this->checkAuthShow();}
		$result = ActionApply(array($this->model,$action),array($this->in['projectID']));
		$this->showProject();
	}
	public function projectFavAdd(){$this->projectAction('favAdd');}
	public function projectFavCancel(){$this->projectAction('favRemove');}
	public function projectArchive(){$this->projectAction('dataArchive',true);}
	public function projectArchiveCancel(){$this->projectAction('dataArchiveCancel',true);}
	public function projectRemove(){$this->projectAction('dataRemove',true);}
	public function projectRemoveCancel(){$this->projectAction('dataRemoveCancel',true);}
	public function projectRemoveForce(){$this->projectAction('removeForce',true);}
	
	// 文件选择时,自动将文件拷贝到项目文件夹内(条件: 必须是文件/启用了项目文件/自己有编辑权限/在项目文件夹外);
	public function fileSelectAutoCopy(){
		$this->checkAuth('edit');
		$fileInfo = IO::info($this->in['filePath']);
		if(!is_array($fileInfo) || $fileInfo['type'] != 'file'){
			show_json('',false);
		}
		if(!Action("explorer.auth")->fileCanRead($fileInfo['path'])){
			show_json(LNG('explorer.noPermissionAction'),false);
		}
		$data = ProjectModelFile::fileSelectAutoCopy($this->model,$fileInfo,$this->in['projectID']);
		show_json($data,!!$data);
	}
	
	// -----------------------------任务操作-----------------------------------
	public function taskProject(){
		$this->checkAuthShow();// 读取权限, 获取项目所有任务列表;
		$allowAll = $this->selfAuthType($this->in['projectID']) == 'admin';
		$result   = $this->modelTask->listTaskAll($this->in['projectID'],$allowAll);
		if(!$result){show_json(LNG('project.tips.emptyProject'),false);}
		show_json($result,true,$this->logChange('project',$result['project']));
	}
	public function taskInfo(){
		$this->checkTask();$this->checkAuthShow();
		$data = $this->modelTask->getInfo($this->in['taskID']);
		show_json($data,!!$data);
	}
	public function taskLog(){
		$this->checkTask();$this->checkAuthShow();
		$data = $this->modelLog->listTask($this->in['taskID'],$this->logParamParse());
		show_json($data,!!$data,$this->logChange('task',false));
	}
	public function taskAdd(){
		$this->checkAuthEdit();
		$data = Input::getArray(array(
			"name"		=> array("check"=>"require"),
			"desc"		=> array("check"=>"require",'default'=>''),
			"projectID"	=> array("check"=>"number"),
			"isList"	=> array("check"=>"in",'default'=>'0','param'=>array('0','1')),
			"pid"		=> array("check"=>"number",'default'=>'0'),
			"ownerUser"	=> array("check"=>"number",'default'=>''),
		));
		if($data['pid'] == '0'){$data['isList'] = '1';}
		if($data['projectID'] == '0'){$data['isList'] = '0';}
		
		$this->checkTaskParent($data['pid'],$data['projectID']);
		$beforeTask = Input::get('beforeTask','require','');// 0=最前面;空=最后面;
		$this->taskCheckDesc($data);
		
		// 已归档已删除任务, 添加子任务保持状态和父任务一致;
		if($data['pid'] && $data['pid'] != 0){
			$taskParent = $this->modelTask->getInfo($data['pid']);
			if($taskParent['status'] != ProjectModelTask::STATUS_DOING){
				$data['_status'] = $taskParent['status'];
			}
		}
		
		$taskID = $this->modelTask->dataAdd($data,$beforeTask);
		Hook::trigger('project.taskAdd.after',$taskID,$data);
		$this->taskUpdate($taskID);
		$this->showTask($taskID);
	}
	public function taskImageLink($taskID,$json){
		if(!isset($json['desc'])){return;}
		$descNew = Action('explorer.attachment')->linkTarget($taskID,$json['desc'],'project_task_desc');
	}
	public function taskImageClear($taskID,$json){
		$descNew = Action('explorer.attachment')->clearTarget($taskID,'project_task_desc');
	}
	
	
	private function taskUpdate($taskID){
		if(isset($this->in['meta']) && $this->in['meta']){
			$allowKeys = $this->modelTask->metaKeysGet($this->getProjectInfo());
			$meta = $this->checkMetaData($this->in['meta'],$allowKeys);
			$this->modelTask->dataSetMeta($taskID,$meta);
		}
		if(isset($this->in['userHas'])){
			$this->modelTask->dataSetUser($taskID,$this->in['userHas']);
		}
	}
	
	private function taskCheckDesc(&$data){
		if(!$data['desc'] || !isset($data['desc'])){return;}
		$data['desc'] = Html::clean($data['desc']);
		$desc = ModelBase::textEncode($data['desc']);
		if(strlen($desc) > 60000){show_json(LNG('common.lengthLimit').' ('.strlen($desc)."/60000)",false);}
	}
	
	public function taskEdit(){ // name,desc,ownerUser; user; meta;
		$taskInfo = $this->checkTaskEdit();
		$data = Input::getArray(array( // 编辑基本信息,该接口不支持直接修改所属项目;
			"name"		=> array("check"=>"require",'default'=>''),
			"desc"		=> array("check"=>"require",'default'=>''),
			"ownerUser"	=> array("check"=>"require",'default'=>''),
		));
		if(!isset($this->in['name'])){unset($data['name']);}
		if(!isset($this->in['desc'])){unset($data['desc']);}
		if(!isset($this->in['ownerUser'])){unset($data['ownerUser']);}

		// 任务为个人tood,强制设置负责人为自己;
		if($taskInfo['projectID'] == '0'){
			$data['ownerUser'] = $taskInfo['createUser'];
		}
		
		$this->taskCheckDesc($data);
		$this->modelTask->dataEdit($this->in['taskID'],$data);
		$this->taskUpdate($this->in['taskID']);
		Hook::trigger('project.taskEdit.after',$this->in['taskID'],$data);
		$this->showTask();
	}
	public function taskSort(){
		$this->checkTaskEdit();
		$data = Input::getArray(array( // 编辑基本信息,该接口不支持直接修改所属项目;
			"beforeTask"	=> array("check"=>"require",'default'=>''),// 0=最前面;空=最后面;
			"pid"			=> array("check"=>"number",'default'=>'0'),
		));
		$this->checkTaskParent($data['pid'],$this->in['projectID']);
		$res = $this->modelTask->dataSetSort($this->in['taskID'],$data['pid'],$data['beforeTask']);
		if(!$res){show_json(LNG('explorer.error'),false);}
		$this->showTask();
	}
	
	// 任务或列表复制; 任务[指定项目,指定列表,前一个任务]; 列表[指定项目,前一个列表]; pid为空则为列表;
	public function taskCopyTo(){
		$taskID = Input::get('taskID','number');
		$data = $this->taskCopyMoveCheck($taskID,'copy');
		$createID = $this->modelTask->taskCopyTo($taskID,$data['projectTo'],$data['pid'],$data['beforeTask'],$data['options']);
		if(!$createID){show_json(LNG('explorer.error'),false);}
		$showTask = ($this->in['projectID'] == $data['projectTo']) ? $createID : $taskID; // 跨项目复制时不处理;
		$this->showTask($showTask,true);
	}
	
	// 任务或列表移动; 任务[指定项目,指定列表,前一个任务]; 列表[指定项目,前一个列表]; pid为空则为列表;
	public function taskMoveTo(){
		$taskID = Input::get('taskID','number');
		$data = $this->taskCopyMoveCheck($taskID,'move');
		$this->modelTask->taskMoveTo($taskID,$data['projectTo'],$data['pid'],$data['beforeTask']);
		$this->showTask();
	}
	private function taskCopyMoveCheck($taskID,$action){
		$data = Input::getArray(array( // 编辑基本信息,该接口不支持直接修改所属项目;
			"projectTo"		=> array("check"=>"number"),
			"beforeTask"	=> array("check"=>"require",'default'=>''),// 0=最前面;空=最后面;
			"pid"			=> array("check"=>"number",'default'=>'0'),
			"options"		=> array("check"=>"json",'default'=>array()),
		));
		
		$this->in['taskID'] = $taskID;
		if($action == 'copy'){
			$this->checkTaskView();
		}else if($action == 'move'){
			$this->checkTaskEdit();
		}
		$isSameProject = $this->in['projectID'] == $data['projectTo'];
		if(!$isSameProject){$this->checkAuth('edit',$data['projectTo']);}
		if($data['pid'] != '0'){
			$pidTask = $this->getTaskInfo($data['pid']);
			if(!$pidTask){show_json(LNG('project.tips.emptyList'),false);}
			if($pidTask['projectID'] != $data['projectTo']){show_json(LNG('project.tips.listNotInProject'),false);}
		}
		return $data;
	}
	private function taskAction($action){
		$this->checkTaskEdit();
		$result = ActionApply(array($this->modelTask,$action),array($this->in['taskID']));
		$this->showTask();
	}
	public function taskArchive(){$this->taskAction('taskArchive');}
	public function taskArchiveCancel(){$this->taskAction('taskArchiveCancel');}
	public function taskRemove(){$this->taskAction('taskRemove');}
	public function taskRemoveCancel(){$this->taskAction('taskRemoveCancel');}
	public function taskRemoveForce(){
		$taskInfo = $this->checkTask();
		$this->checkAuthAdmin(); // 彻底删除需要管理员权限;
		Hook::trigger('project.taskRemove.after',$this->in['taskID'],array());
		$this->taskAction('taskRemoveForce');
	}
	
	
	// 批量添加任务( ownerUser/userHas/meta; statusAction)
	public function taskAddMutil(){
		$this->checkAuthEdit();
		$taskArr = json_decode(_get($this->in,'taskArr',''),true);
		$taskAdd = $this->modelTask->dataAddMutilAndChild($taskArr,$this->in['projectID']);

		$code = $taskAdd ? true : false;
		$data = $taskAdd ? $taskAdd : LNG('explorer.error');
		show_json($data,$code,$this->logChange('task',false));
	}
	
	// 批量编辑任务( ownerUser/userHas/meta; statusAction)
	public function taskEditMutil(){
		$actionAllow = array('taskArchive','taskArchiveCancel','taskRemove','taskRemoveCancel','taskRemoveForce');
		$taskArr = json_decode(_get($this->in,'taskArr',''),true);
		if(!is_array($taskArr) || !$taskArr){
			show_json(LNG('explorer.notNull'),false);
		}
		// 批量编辑; 指定了每个任务信息时独立处理;  taskArrSet:{taskIDXXX:{ownerUser:,...,meta:{...},statusAction:xxx },...}
		$taskArrSet = isset($this->in['taskArrSet']) ? json_decode($this->in['taskArrSet'],true) : false;		
		// pr($taskArr,$action,$this->in);exit;
		
		foreach($taskArr as $taskID){
			$this->in['taskID'] = $taskID;
			if(is_array($taskArrSet)){ // 独立处理,参数覆盖;
				$editChange = $taskArrSet[$taskID];
				if(!$editChange){continue;}
				foreach($editChange as $key => $value){
					$this->in[$key] = is_array($value) ? json_encode($value) : $value;
				}
			}
			
			$this->checkTaskEdit();
			if(isset($this->in['ownerUser'])){
				$data = array('ownerUser'=>$this->in['ownerUser']);
				$this->modelTask->dataEdit($taskID,$data);
			}
			$this->taskUpdate($taskID);
			$action = Input::get('statusAction','in','',$actionAllow);
			if($action){
				ActionApply(array($this->modelTask,$action),array($taskID));
			}
		}
		ProjectModelLog::logAddClear();
		show_json(LNG('explorer.success'),true,$this->logChange('task',false));
	}
	
	// 批量移动复制任务;
	public function taskCopyMoveMutil(){
		$taskArr = json_decode(_get($this->in,'taskArr',''));
		$action  = _get($this->in,'copyMoveAction','');// copy/move
		if(!$action || !is_array($taskArr) || !$taskArr){
			show_json(LNG('explorer.notNull'),false);
		}

		// 批量复制/移动; 指定了每个任务信息时独立处理;  taskArrSet:{taskIDXXX:{projectTo,beforeTask,pid,options,  copyMoveAction:xxx },...}
		$taskArrSet = isset($this->in['taskArrSet']) ? json_decode($this->in['taskArrSet'],true) : false;		
		// pr($taskArr,$action,$this->in);exit;
		
		$success = 0;$taskResult = array();
		foreach ($taskArr as $taskID){
			if(is_array($taskArrSet)){ // 独立处理,参数覆盖;
				$editChange = $taskArrSet[$taskID];
				if(!$editChange){continue;}
				foreach($editChange as $key => $value){
					$this->in[$key] = is_array($value) ? json_encode($value) : $value;
				}
			}
			
			$data = $this->taskCopyMoveCheck($taskID,$action);
			if(is_array($data['options']) && isset($data['options']['name'])){
				unset($data['options']['name']);// 多选复制时,屏蔽指定任务名称;
			}
			if($action == 'copy'){
				$res  = $this->modelTask->taskCopyTo($taskID,$data['projectTo'],$data['pid'],$data['beforeTask'],$data['options']);
				if($res){$taskResult[] = $res.'';}
			}else if($action == 'move'){
				$res  = $this->modelTask->taskMoveTo($taskID,$data['projectTo'],$data['pid'],$data['beforeTask']);
				if($res){$taskResult[] = $taskID.'';}
			}
			// trace_log([$res,$taskID]);
			if($res){$success++;}
		}
		$code = $success > 0 ? true : false;
		$text = $code ? LNG('explorer.success') : LNG('explorer.error');
		$out  = array('msg'=>$text,'taskResult'=>$taskResult);
		ProjectModelLog::logAddClear();
		show_json($out,$code,$this->logChange('task',false));
	}
	

	// 评论权限检测处理;
	public function commentCheckType($targetType,$targetID,$param){
		$this->loadModelNow();
		$allowType = array(ProjectModel::COMMENT_TYPE_PROJECT,ProjectModel::COMMENT_TYPE_PROJECT_TASK);
		$checkKey = 'comment.checkType.'.$targetType.'.'.$targetID.'.'.$param;
		if(!in_array($targetType,$allowType) || !$targetID) return;
		$GLOBALS[$checkKey] = true;
	}
	
	// 评论权限检测; $action=view,edit,remove [项目:是否允许讨论--取决于是否开启讨论引用; 任务是否允许讨论--取决于是否禁用了任务评论]
	public function commentCheckAuth($targetType,$targetID,$authCheck){
		$this->loadModelNow();
		$allowType = array(ProjectModel::COMMENT_TYPE_PROJECT,ProjectModel::COMMENT_TYPE_PROJECT_TASK);
		if(!in_array($targetType,$allowType) || !$targetID) return;
		
		if($targetType == ProjectModel::COMMENT_TYPE_PROJECT){
			$this->in['projectID'] = $targetID;
			if(!$this->model->checkAllowChat($targetID)){
				show_json(LNG('project.tips.chatNotOpen'),false);
			}
		}
		if($targetType == ProjectModel::COMMENT_TYPE_PROJECT_TASK){
			$taskInfo = $this->getTaskInfo($targetID);
			if(!$taskInfo){show_json(LNG('project.tips.emptyTask'),false);}
			$this->in['projectID'] = $taskInfo['projectID'];
			if(!$this->model->checkAllowTaskChat($this->in['projectID'])){
				show_json(LNG('project.tips.chatNotEnable'),false);
			}
		}
		
		// 自己为项目编辑者时,允许删除自己的评论
		$action = strtolower(ACT);
		if($action == 'remove' || $action == 'edit'){
			$info = Model("Comment")->where(array("commentID"=>$this->in['id']))->find();
			if($info && $info['userID'] == USER_ID){
				$this->checkAuthEdit();
				$this->commentChangeLog($targetType,$targetID,$authCheck,$info);
				return;
			}
			return;
		}

		$actionAuthMap = array('view'=>'show','edit'=>'edit','remove'=>'admin');
		$this->checkAuth($actionAuthMap[$authCheck]);
		$this->commentChangeLog($targetType,$targetID,$authCheck);
	}
	
	// 评论添加/删除;变更日志记录;
	private function commentChangeLog($targetType,$targetID,$authCheck,$commentInfo = false){
		$checkKey  = 'comment.checkAuth.'.$targetType.'.'.$targetID.'.'.$authCheck;
		$GLOBALS[$checkKey] = true;
		
		$action = strtolower(ACT);
		$commentEvent = 'comment.'.$action;
		if(!in_array($action,array('add','edit','remove'))){return;}
		
		$dataLog = array('content' => _get($this->in,'content',''));
		if($commentInfo && $action == 'edit'){
			$dataLog['contentBefore'] = $commentInfo['content'];
		}
		if($commentInfo && $action == 'remove'){
			$dataLog['content'] = $commentInfo['content'];
		}
		
		if($targetType == ProjectModel::COMMENT_TYPE_PROJECT_TASK){
			$this->modelTask->addLog($this->in['projectID'],$targetID,$commentEvent,$dataLog);
		}else{// 项目讨论,记录日志到项目日志中(暂不不记录)
			//$this->model->addLog($targetID,$commentEvent,$dataLog);
		}
		// trace_log([$action,$commentEvent,$dataLog,$targetID,$commentInfo]);
	}
	
	
	// 是否允许删除或修改自己的评论;默认允许(统一在commentCheckAuth中判断权限;)
	// 删除权限: 预览者=无权限;编辑者=仅支持删除自己的评论;拥有者=支持删除所有人评论;
	public function commentCheckSelf($targetType,$targetID,$action){
		$checkKey = 'comment.checkSelf.'.$targetType.'.'.$targetID.'.'.$action;
		$GLOBALS[$checkKey] = true;
	}
	
	private function showProject($dataID=false){
		$dataID   = $dataID ? $dataID : $this->in['projectID'];
		$dataInfo = $this->getProjectInfo($dataID);
		show_json($dataInfo,true,$this->logChange('project',$dataInfo));
	}
	private function showTask($dataID=false,$getChildren=false){
		$dataID   = $dataID ? $dataID : $this->in['taskID'];
		if($getChildren){
			$dataInfo = $this->modelTask->getInfoWithChildren($dataID);
		}else{
			$dataInfo = $this->modelTask->getInfo($dataID);
		}
		show_json($dataInfo,true,$this->logChange('task',$dataInfo));
	}
	
	// 变更日志(从上次logID之后的更新; 排除当前请求产生的日志; 查询出任务变更的任务列表,前端做整理处理);
	private function logChange($changeType,$data=false){
		$projectID = $this->in['projectID'];
		$log = $this->modelLog->logChange($projectID,$this->in['lastLogID']);
		if(!$log['logList']){return $log;}
		
		$log['project'] = false;$taskArr = array();
		foreach($log['logList'] as $item){
			if($item['taskID'] == '0'){$log['project'] = $projectID;continue;}
			if(in_array($item['taskID'],$taskArr)){continue;}
			$taskArr[] = $item['taskID'];
		}
		
		if($log['project']){
			$projectInfo = ($changeType == 'project' && $data) ? $data:false;
			if(!$projectInfo){$projectInfo = $this->getProjectInfo($projectID);}
			$log['project'] = $projectInfo;
		}

		if($taskArr){
			$taskIsAdd = $changeType == 'task' && is_array($data) && in_array($data['taskID'],$taskArr);
			if($taskIsAdd && count($taskArr) == 1 ){
				$log['task'] = array($data);
			}else{
				$log['task'] = $this->modelTask->listTasks($projectID,$taskArr);
			}
		}
		return $log;
	}
	
	private function getProjectInfo($projectID=false){
		$projectID = $projectID ? $projectID:Input::get('projectID','number');
		return $this->model->getInfo($projectID);
	}
	private function getTaskInfo($taskID=false){
		$taskID = $taskID ? $taskID:Input::get('taskID','number');
		return $this->modelTask->getInfo($taskID);
	}
	// 任务检测; taskID是否为数字,任务是否存在,任务是否在当前项目中检测;
	private function checkTask(){
		$taskInfo = $this->getTaskInfo();
		if(!$taskInfo){show_json(LNG('project.tips.emptyTask'),false);}
		$this->in['projectID'] = $taskInfo['projectID'];
		return $taskInfo;
	}
	
	// 父任务检测; 是否存在,且在同一个项目;
	private function checkTaskParent($pid,$projectID){
		if(!$pid || $pid == 0) return;
		$taskParent = $this->modelTask->getInfo($pid);
		if(!$taskParent){show_json(LNG('project.tips.emptyTaskPid'),false);}
		if($taskParent['projectID'] == '0'){
			if($taskInfo['projectID'] == '0' && $taskInfo['createUser'] != KodUser::id()){
				show_json(LNG('project.tips.notInProject'),false);
			}
			return;
		}
		if($taskParent['projectID'] != $projectID){
			show_json(LNG('project.tips.taskNotInProject'),false);
		}
	}
	private function checkTaskEdit(){
		$taskInfo = $this->checkTask();
		$this->checkAuthEdit();
		
		// 任务为个人tood,仅自己可以读写;
		if($taskInfo['projectID'] == '0' && $taskInfo['createUser'] != KodUser::id()){
			show_json(LNG('project.tips.notInProject'),false);
		}
		return $taskInfo;
	}
	private function checkTaskView(){
		$taskInfo = $this->checkTask();
		$this->checkAuthShow();
		// 任务为个人tood,仅自己可以读写;
		if($taskInfo['projectID'] == '0' && $taskInfo['createUser'] != KodUser::id()){
			show_json(LNG('project.tips.notInProject'),false);
		}
		return $taskInfo;
	}
	
	// 检测是否允许创建项目(系统管理员/项目管理员不检测;是否开启了允许用户创建项目; 用户是否达到创建项目上限);
	private function checkAddProject(){
		if($this->isAdmin){return true;}
		$userAllowCreate = _get($this->options,'userAllowCreate','');
		if($userAllowCreate !== '' && $userAllowCreate === '0'){
			show_json(LNG('project.tips.notAllowCreate'),false);
		}
		$totalProject = $this->model->where(array('createUser'=>kodUser::id()))->count();
		if(intval(_get($this->options,'userCreateMax',10)) < $totalProject){
			show_json(LNG('project.tips.createLimit'),false);
		}
		return true;
	}
	
	// 读写权限检测; 不存在处理;  show:[不登录须项目设置为公开;或自己在该项目中]; 
	// view/edit/admin; 须自己在该项目成员中; 并且权限大于等于该权限;
	private function checkAuth($type,$projectID=false){
		if($this->isAdmin){return true;}
		if($type == 'view'){$type = 'show';}
		
		$userID	= KodUser::id();
		$projectID = $projectID ? $projectID:Input::get('projectID','number');
		if(!$projectID || $projectID == '0'){
			if(!$userID){show_json(LNG('user.loginFirst'),ERROR_CODE_LOGOUT);}
			return;
		}
		$selfAuth = $this->selfAuthType($projectID);
		if($type == 'show'  && ($selfAuth == 'show' || $selfAuth == 'edit' || $selfAuth == 'admin')){return;}
		if($type == 'edit'  && ($selfAuth == 'edit' || $selfAuth == 'admin')){return;}
		if($type == 'admin' && ($selfAuth == 'admin')){return;}
		if(!$userID){show_json(LNG('user.loginFirst'),ERROR_CODE_LOGOUT);}
		show_json(LNG('explorer.noPermissionAction'),false);
	}
	
	// 返回自己在该项目的权限 show/edit/admin
	private function selfAuthType($projectID){
		if($this->isAdmin){return 'admin';}

		$userID	= KodUser::id();
		$projectInfo = $this->getProjectInfo($projectID);
		if(!$projectInfo){show_json(LNG('project.tips.emptyProject'),false);}
		if($this->model->isTemplate($projectInfo)){return 'show';}
		
		$userList = $projectInfo['dataInfo']['userList'];
		$isPublic = $projectInfo['metaInfo']['authType'] == 'public';
		if(!$userID || !is_array($userList[$userID])){return $isPublic ? 'show':false;}
		
		$authType = $userList[$userID]['authType'];
		if($authType == ProjectModel::AUTH_READ){return 'show';}
		if($authType == ProjectModel::AUTH_WRITE){return 'edit';}
		if($authType == ProjectModel::AUTH_ADMIN){return 'admin';}
	}
	private function checkAuthShow(){return $this->checkAuth('show');}
	private function checkAuthEdit(){return $this->checkAuth('edit');}
	private function checkAuthAdmin(){return $this->checkAuth('admin');}
	
	
	
	// =============================管理员操作接口===============================
	private function adminCheck($ignoreOut = false){
		if(kodUser::isRoot()){return true;}
		$userAdmin = _get($this->options,'userAdmin','');
		$userAdmin = $userAdmin ? explode(',',$userAdmin):array();
		if($userAdmin && in_array(kodUser::id(),$userAdmin)){return true;}
		
		if($ignoreOut){return false;}
		show_json(LNG('explorer.noPermissionAction'),false);
	}
	public function adminInfo(){
		$this->adminCheck();
		show_json($this->modelAdmin->adminInfo());
	}
	public function adminList(){
		$this->adminCheck();
		$param = Input::getArray(array(
			"userID"		=> array("check"=>"number",'default'=>''),
			"timeFrom"		=> array("check"=>"number",'default'=>''),
			"timeTo"		=> array("check"=>"number",'default'=>''),
			"status"		=> array("check"=>"require",'default'=>''),
			'words'			=> array("check"=>"require",'default'=>''),
			
			'sortField'		=> array("check"=>"require",'default'=>''),
			'sortType'		=> array("check"=>"in",'default'=>'up','param'=>array('up','down')),
		));
		$res = $this->modelAdmin->listProject($param);
		show_json($res,true);
	}
	public function adminLog(){
		$this->adminCheck();
		$param = Input::getArray(array(
			"userID"		=> array("check"=>"number",'default'=>''),
			"timeFrom"		=> array("check"=>"number",'default'=>''),
			"timeTo"		=> array("check"=>"number",'default'=>''),
			"logType"		=> array("check"=>"require",'default'=>''),
			"projectID"		=> array("check"=>"number",'default'=>''),
			
			'sortField'		=> array("check"=>"require",'default'=>''),
			'sortType'		=> array("check"=>"in",'default'=>'up','param'=>array('up','down')),
		));
		$res = $this->modelAdmin->listLog($param);
		if($res && is_array($res['list'])){
			$projectArr = array_to_keyvalue($res['list'],'','projectID');
			$taskArr    = array_to_keyvalue($res['list'],'','taskID');
			$res['projectList'] = $this->modelAdmin->listProjectSimple($projectArr);
			$res['taskList']    = $this->modelTask->listTasksSimple($taskArr);
			$res['projectList']['0'] = $this->modelSelf->projectUserTodo();
		}
		show_json($res,true);
	}
	public function adminOption(){
		$this->adminCheck();
		$allowKeys = explode(',','taskCheck,taskStatus,taskLevel,taskBug,disableComment,cardOpenType,'.
								 'applicationSelect,allowProjectGroup,userField,userAllowCreate,userCreateMax,userAdmin');
		$options = array_field_key($this->in,$allowKeys);
		if($options){$this->setConfig($options);}
		show_json(LNG('explorer.success'),true,$this->getConfig());
	}
	
	// =============================项目分组操作===============================
	private function getModelGroup(){
		// 模版分组接口及model复用; 项目分组/模版分类;
		if($this->in['groupType'] == 'projectTemplate'){
			return $this->modelGroupTemplate;
		}
		return $this->modelGroup;
	}
	public function groupList(){
		// KodUser::checkLogin();
		show_json($this->getModelGroup()->listData(),true);
	}
	public function groupAdd(){
		$this->adminCheck();
		$param = Input::getArray(array(
			"name"		=> array("check"=>"require"),
			"desc"		=> array("check"=>"require",'default'=>''),
			"user"		=> array("check"=>"require",'default'=>''),
			"pid"		=> array("check"=>"number",'default'=>'0'),
		));
		$res = $this->getModelGroup()->add($param);
		$this->groupInfoShow($res);
	}
	public function groupEdit(){
		$this->adminCheck();
		$id = Input::get('id','number');
		$param = Input::getArray(array(
			"name"		=> array("check"=>"require"),
			"desc"		=> array("check"=>"require",'default'=>''),
			"user"		=> array("check"=>"require",'default'=>''),
			"pid"		=> array("check"=>"number",'default'=>'0'),
			"templateSort"	=> array("check"=>"require",'default'=>''),
		));
		$res = $this->getModelGroup()->update($id,$param);
		$this->groupInfoShow($res);
	}
	public function groupRemove(){
		$this->adminCheck();
		$id = Input::get('id','number');
		$res = $this->getModelGroup()->remove($id);
		$this->groupInfoShow($res);
	}
	public function groupSort(){
		$this->adminCheck();
		$param = Input::getArray(array(
			"id"		=> array("check"=>"require"),
			"pid"		=> array("check"=>"number",'default'=>'0'),
			"beforeID"	=> array("check"=>"require",'default'=>''), // first=>最前面;id后; 为空则最后
		));
		$res = $this->getModelGroup()->sort($param['id'],$param['pid'],$param['beforeID']);
		$this->groupInfoShow($res);
	}
	
	private function groupInfoShow($res){
		if(!$res){show_json(LNG('explorer.error'),false);}
		$this->groupList();
	}
}
