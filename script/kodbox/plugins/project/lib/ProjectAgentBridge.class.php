<?php
/**
 * KodCloud 项目插件的 Agent 只读桥接层。
 *
 * 文件职责：
 * 1. 校验 Java 侧签发的短期 HMAC 票据；
 * 2. 复用项目插件的成员权限、任务隐私和完成状态逻辑；
 * 3. 输出不包含令牌、路径和下载地址的稳定 JSON；
 * 4. 为 Java Project Provider 提供项目、任务、日志和资料元数据。
 *
 * 重要边界：
 * - 本类只读，不创建、修改、删除项目、任务或文件；
 * - KodCloud accessToken 永远不会出现在响应和日志中；
 * - 文件正文读取仍需项目权限和 explorer.auth 二次校验。
 */
class ProjectAgentBridge{
	private $plugin;
	private $claims;

	public function __construct($plugin){$this->plugin = $plugin;}

	/** 分发只读动作。项目动作与制度库动作都必须先通过短期票据校验。 */
	public function dispatch($action){
		$this->claims = $this->verifyTicket();
		switch($action){
			case 'projects': $this->json($this->listProjects()); break;
			case 'snapshot': $this->json($this->snapshot($this->number('projectID'))); break;
			case 'tasks': $this->json($this->tasks($this->number('projectID'))); break;
			case 'activity': $this->json($this->activity($this->number('projectID'))); break;
			case 'documents': $this->json($this->documents($this->number('projectID'))); break;
			case 'document': $this->documentContent($this->number('projectID'),$this->number('fileID')); break;
			case 'policy_documents': $this->json($this->policyDocuments($this->number('folderID'))); break;
			case 'policy_document': $this->policyDocumentContent($this->number('folderID'),$this->number('fileID')); break;
			default: show_json('Agent 项目桥接动作不支持',false);
		}
	}

	/** 列出当前 KodCloud 用户作为项目成员可访问的正常项目。 */
	private function listProjects(){
		$userID = $this->userID();
		$rows = Model('plugin_project_user')->where(array('taskID'=>0,'userID'=>$userID))->select();
		$ids = array_unique(array_filter(array_to_keyvalue($rows,'','projectID')));
		$result = array();
		foreach($ids as $projectID){
			$info = $this->project($projectID);
			if(!$info || intval(_get($info,'status')) != ProjectModel::STATUS_DOING){continue;}
			$result[] = $this->projectSummary($info,$userID);
		}
		return array('userID'=>$userID,'items'=>$result,'total'=>count($result),'asOf'=>time());
	}

	/** 读取项目基础信息、成员、配置、任务汇总、日志和资料目录状态。 */
	private function snapshot($projectID){
		$info = $this->authorizedProject($projectID);
		$userID = $this->userID();
		$tasks = $this->taskData($projectID,$info,$userID);
		return array(
			'project'=>$this->projectSummary($info,$userID),
			'config'=>array(
				'authType'=>_get($info,'metaInfo.authType','private'),
				'taskFinishType'=>_get($info,'metaInfo.taskFinishType','taskCheck'),
				'taskFinishDiy'=>_get($info,'metaInfo.taskFinishDiy',array()),
				'taskShowOnlySelf'=>_get($info,'metaInfo.taskShowOnlySelf','0'),
				'progress'=>_get($info,'metaInfo.progress',null),
				'timeFrom'=>_get($info,'metaInfo.timeFrom',null),
				'timeTo'=>_get($info,'metaInfo.timeTo',null),
			),
			'members'=>$this->members($info),
			// Java 侧统计必须使用与单独 tasks 接口完全一致的可见任务树。
			// 不在这里重新查库，避免 taskShowOnlySelf 在两条数据链路上出现偏差。
			'tasks'=>$tasks,
			'taskSummary'=>$this->taskSummary($tasks,$info),
			'activity'=>$this->activityData($projectID,$tasks),
			'documents'=>$this->documentList($info),
			'asOf'=>time(),
		);
	}

	/** 单独读取任务列表；用于统计模块避免重复下载项目详情。 */
	private function tasks($projectID){
		$info = $this->authorizedProject($projectID);
		$tasks = $this->taskData($projectID,$info,$this->userID());
		return array('projectID'=>$projectID,'tasks'=>$tasks,'summary'=>$this->taskSummary($tasks,$info),'asOf'=>time());
	}

	/** 读取项目/任务日志并只返回当前用户可见任务的活动。 */
	private function activity($projectID){
		$info = $this->authorizedProject($projectID);
		$tasks = $this->taskData($projectID,$info,$this->userID());
		return array('projectID'=>$projectID,'items'=>$this->activityData($projectID,$tasks),'asOf'=>time());
	}

	/** 返回项目文件夹中的脱敏元数据；不返回路径、分享 URL 和令牌。 */
	private function documents($projectID){
		$info = $this->authorizedProject($projectID);
		return array('projectID'=>$projectID,'role'=>$this->role($info,$this->userID()),'items'=>$this->documentList($info),'asOf'=>time());
	}

	/**
	 * 读取文件正文。只允许 Java 侧同步任务调用，且再次确认项目成员和文件可读权限。
	 * KodCloud 不支持正文时返回结构化错误，而不是把二进制或路径泄露给模型。
	 */
	private function documentContent($projectID,$fileID){
		$info = $this->authorizedProject($projectID);
		$file = $this->findDocument($info,$fileID);
		if(!$file || !_get($file,'path') || _get($file,'type') !== 'file'){
			show_json('项目文件不存在或当前用户无权读取',false);return;
		}

		// fileStorePath 可能是 {source:...} 或 {shareItem:...} 等 KodCloud 虚拟路径。
		// 不能传给 PHP 原生 file_get_contents；IO::getContent 会通过 KodCloud 的
		// 存储驱动解析本地、对象存储和虚拟来源，且文件已由 authorizedProject +
		// findDocument 限定在当前项目的资料目录中。
		$size = intval(_get($file,'size',0));
		if($size > $this->documentReadMaxBytes()){
			show_json('项目文件超过桥接读取大小限制',false);return;
		}
		try{$content = IO::getContent($file['path']);}catch(Exception $e){$content = false;}
		if($content === false){show_json('项目文件暂不支持正文读取',false);return;}

		// DOCX、XLSX、PDF 都可能包含二进制字节。统一 Base64 后再放入 JSON，
		// Java 导入任务按 contentEncoding 解码，避免 JSON/UTF-8 破坏原始内容。
		show_json(array(
			'projectID'=>$projectID,
			'fileID'=>$fileID,
			'name'=>_get($file,'name',''),
			'mime'=>$this->documentMime($file),
			'contentEncoding'=>'base64',
			'contentBase64'=>base64_encode($content),
			'contentBytes'=>strlen($content),
			'contentHash'=>hash('sha256',$content),
		),true);
	}

	/**
	 * 列出管理员绑定的共享制度目录。调用方身份是 Java 签发的只读服务账号票据，
	 * KodCloud 仍会按该账号的目录权限重新校验；响应不包含路径和下载链接。
	 */
	private function policyDocuments($folderID){
		$rows = $this->policyDocumentRows($folderID);
		return array('folderID'=>$folderID,'items'=>$this->documentProjection($rows),'asOf'=>time());
	}

	/** 读取共享制度目录中已枚举文件的正文；禁止借此读取目录外任意文件。 */
	private function policyDocumentContent($folderID,$fileID){
		$file = false;
		foreach($this->policyDocumentRows($folderID) as $item){
			if(is_array($item) && (string)_get($item,'sourceID',_get($item,'fileID')) === (string)$fileID){$file = $item;break;}
		}
		if(!$file || !_get($file,'path') || _get($file,'type') !== 'file'){
			show_json('制度文件不存在或服务账号无权读取',false);return;
		}
		$size = intval(_get($file,'size',0));
		if($size > $this->documentReadMaxBytes()){
			show_json('制度文件超过桥接读取大小限制',false);return;
		}
		try{$content = IO::getContent($file['path']);}catch(Exception $e){$content = false;}
		if($content === false){show_json('制度文件暂不支持正文读取',false);return;}
		show_json(array(
			'folderID'=>$folderID,'fileID'=>$fileID,'name'=>_get($file,'name',''),
			'mime'=>$this->documentMime($file),'contentEncoding'=>'base64',
			'contentBase64'=>base64_encode($content),'contentBytes'=>strlen($content),
			'contentHash'=>hash('sha256',$content),
		),true);
	}

	private function taskData($projectID,$info,$userID){
		$role = $this->role($info,$userID);
		// Agent 查询必须保持真正只读：不要触发项目插件为页面准备附件目录的初始化。
		$result = $this->plugin->modelTask->listTaskAllForUser($projectID,$role === 'admin',$userID,false);
		return _get($result,'taskList',array());
	}

	private function taskSummary($groups,$info){
		$flat = array();$this->flattenTasks($groups,$flat);
		$effective = array();
		foreach($flat as $task){
			if(intval(_get($task,'isList',0)) == 1 || intval(_get($task,'status',1)) != 1){continue;}
			$effective[] = $task;
		}
		$done = 0;$overdue = 0;$noOwner = 0;$now = time();
		foreach($effective as $task){
			if($this->plugin->modelTask->taskFinished($task,$info)){$done++;continue;}
			if(!_get($task,'ownerUser')){$noOwner++;}
			$deadline = _get($task,'metaInfo.timeTo',_get($task,'timeTo',null));
			if($deadline && is_numeric($deadline) && intval($deadline) < $now){$overdue++;}
		}
		return array('total'=>count($effective),'completed'=>$done,'incomplete'=>count($effective)-$done,'overdue'=>$overdue,'withoutOwner'=>$noOwner,'completionRate'=>count($effective) ? round($done / count($effective),4) : null);
	}

	private function flattenTasks($items,&$result){
		foreach((array)$items as $task){
			if(!is_array($task)){continue;}
			$result[] = $task;
			if(isset($task['children']) && is_array($task['children'])){$this->flattenTasks($task['children'],$result);}
		}
	}

	private function activityData($projectID,$tasks){
		$where = array('projectID'=>$projectID);
		$page = $this->plugin->modelLog->listProject($projectID,$where);
		$items = _get($page,'list',array());
		$visible = array();$flat = array();$this->flattenTasks($tasks,$flat);
		foreach($flat as $task){$visible[(string)_get($task,'taskID')] = true;}
		$out = array();
		foreach((array)$items as $item){
			if(intval(_get($item,'taskID',0)) !== 0 && empty($visible[(string)_get($item,'taskID')])){continue;}
			$out[] = array('id'=>_get($item,'id'),'taskID'=>_get($item,'taskID',0),'userID'=>_get($item,'userID'),'logType'=>_get($item,'logType'),'createdAt'=>_get($item,'createTime'),'description'=>_get($item,'desc',''));
		}
		return $out;
	}

	/**
	 * 返回项目资料目录中的文件元数据。
	 *
	 * 只返回给 Java/Agent 必要的稳定字段，不返回 KodCloud path、下载地址、
	 * shareHash 或 accessToken。真实路径仅在本次 PHP 请求内用于 IO::getContent。
	 */
	private function documentList($info){
		$rows = $this->projectDocumentRows($info);
		return $this->documentProjection($rows);
	}

	/** 把 KodCloud 文件对象投影成稳定元数据，统一项目资料和制度库输出口径。 */
	private function documentProjection($rows){
		$out = array();
		foreach((array)$rows as $item){
			if(!is_array($item) || _get($item,'type') !== 'file'){continue;}
			$fileID = _get($item,'sourceID',_get($item,'fileID'));
			if(!$fileID){continue;}
			$name = _get($item,'name','');
			$out[] = array(
				'fileID'=>$fileID,
				'name'=>$name,
				'size'=>intval(_get($item,'size',0)),
				'mimeType'=>$this->documentMime($item),
				'modifiedAt'=>_get($item,'modifyTime',_get($item,'modify_time',null)),
				'contentHash'=>$this->documentHash($item),
				'version'=>$this->documentVersion($item),
				'supported'=>preg_match('/\.(pdf|docx|xlsx|txt|md)$/i',(string)$name) === 1,
			);
		}
		return $out;
	}

	/**
	 * 递归列出共享制度目录。folderID 只在本次请求内解析为 KodCloud 虚拟路径，
	 * 不会进入 Java、索引或 Agent 响应。
	 */
	private function policyDocumentRows($folderID){
		if(!$folderID){return array();}
		$sourceInfo = false;
		try{$sourceInfo = Model('Source')->pathInfo($folderID);}catch(Exception $e){$sourceInfo = false;}
		$root = _get($sourceInfo,'path','');
		if(!$root){$root = KodIO::make($folderID);}
		try{$exists = IO::exist($root);}catch(Exception $e){$exists = false;}
		if(!$exists){return array();}
		return $this->crawlDocumentRows($root);
	}

	/** 统一的只读目录遍历，限制文件总数防止恶意或误配置目录拖垮进程。 */
	private function crawlDocumentRows($root){
		$pending = array($root);$files = array();$visited = array();$limit = 10000;
		while($pending && count($files) < $limit){
			$path = array_shift($pending);
			if(!$path || isset($visited[$path])){continue;}
			$visited[$path] = true;
			try{$data = IO::listPath($path);}catch(Exception $e){$data = false;}
			if(!is_array($data)){continue;}
			foreach((array)_get($data,'fileList',array()) as $file){
				if(is_array($file) && _get($file,'type') === 'file'){$files[] = $file;}
			}
			foreach((array)_get($data,'folderList',array()) as $folder){
				$folderPath = _get($folder,'path','');
				if(is_array($folder) && $folderPath){$pending[] = $folderPath;}
			}
		}
		return $files;
	}

	private function findDocument($info,$fileID){
		if(!$fileID){return false;}
		$rows = $this->projectDocumentRows($info);
		foreach((array)$rows as $item){if(is_array($item) && (string)_get($item,'sourceID',_get($item,'fileID')) === (string)$fileID){return $item;}}
		return false;
	}

	/**
	 * 从项目专属资料目录递归列出文件。
	 *
	 * 项目插件创建并维护 fileStorePath，成员变更时 ProjectModelFile 会用同一份
	 * dataInfo.userList 更新其分享权限。桥接层先在 authorizedProject 校验成员，
	 * 再只遍历该可信目录，避免 Java 传入任意 KodCloud 路径。
	 */
	private function projectDocumentRows($info){
		$root = _get($info,'metaInfo.fileStorePath',_get($info,'metaInfo.fileSourcePath',''));
		try{$exists = IO::exist($root);}catch(Exception $e){$exists = false;}
		if(!$root || !$exists){return array();}

		return $this->crawlDocumentRows($root);
	}

	/** 返回文档 MIME；插件旧版本没有 mimeType 时以文件扩展名提供稳定兜底。 */
	private function documentMime($file){
		$mime = _get($file,'mimeType',_get($file,'mime',''));
		if($mime){return $mime;}
		$ext = strtolower(pathinfo((string)_get($file,'name',''),PATHINFO_EXTENSION));
		$map = array('pdf'=>'application/pdf','docx'=>'application/vnd.openxmlformats-officedocument.wordprocessingml.document','xlsx'=>'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','txt'=>'text/plain','md'=>'text/markdown');
		return _get($map,$ext,'application/octet-stream');
	}

	/** 采用 KodCloud 内容哈希；没有驱动哈希时返回 null，不能伪造文件版本。 */
	private function documentHash($file){
		$hash = _get($file,'hash',_get($file,'contentHash',null));
		if($hash){return $hash;}
		try{return KodIO::hashPath($file);}catch(Exception $e){return null;}
	}

	/** 文件版本用于增量同步：内容哈希优先，缺失时退化到修改时间和大小。 */
	private function documentVersion($file){
		$hash = $this->documentHash($file);
		if($hash){return $hash;}
		return implode(':',array(_get($file,'sourceID',_get($file,'fileID','')),intval(_get($file,'modifyTime',0)),intval(_get($file,'size',0))));
	}

	/** 限制单文件桥接读取量，避免一次同步耗尽 PHP 进程内存。默认 20 MB。 */
	private function documentReadMaxBytes(){
		$configured = intval(_get($this->plugin->options,'agentDocumentReadMaxBytes',20 * 1024 * 1024));
		return $configured > 0 ? $configured : 20 * 1024 * 1024;
	}

	private function members($info){
		$out = array();
		foreach((array)_get($info,'dataInfo.userList',array()) as $member){
			$user = _get($member,'userInfo',array());
			// 旧版项目数据只保存 userID/authType；按编号读取昵称，仍只投影展示名。
			if(!$user && _get($member,'userID')){
				try{$user = Model('User')->getInfo(_get($member,'userID'));}catch(Exception $e){$user = array();}
			}
			$out[] = array(
				'userID'=>_get($member,'userID'),
				// 用户对象字段会因 KodCloud 版本不同而不同；只投影展示名，
				// 不把邮箱、部门、头像路径等无关个人信息交给 Agent。
				'name'=>_get($user,'nickName',_get($user,'name',_get($user,'userName',''))),
				'authType'=>_get($member,'authType'),
			);
		}
		return $out;
	}

	private function projectSummary($info,$userID){
		return array('projectID'=>_get($info,'projectID'),'name'=>_get($info,'name',''),'description'=>_get($info,'desc',''),'status'=>_get($info,'status'),'role'=>$this->role($info,$userID),'createdAt'=>_get($info,'createTime'),'updatedAt'=>_get($info,'modifyTime'));
	}

	private function authorizedProject($projectID){
		if(!$projectID){show_json('项目编号不能为空',false);}
		$info = $this->project($projectID);
		if(!$info || !$this->canView($info,$this->userID())){show_json('项目不存在或当前用户无权访问',false);}
		return $info;
	}

	private function canView($info,$userID){return $this->role($info,$userID) !== false;}

	private function role($info,$userID){
		$list = (array)_get($info,'dataInfo.userList',array());
		foreach($list as $member){if((string)_get($member,'userID') === (string)$userID){$type = intval(_get($member,'authType',1));return $type >= 3 ? 'admin' : ($type == 2 ? 'write' : 'read');}}
		return _get($info,'metaInfo.authType') === 'public' ? 'public' : false;
	}

	private function project($id){return $this->plugin->model->getInfo($id);}
	private function userID(){return intval(_get($this->claims,'userId',0));}
	private function number($key){return intval(_get($this->plugin->in,$key,0));}

	private function verifyTicket(){
		// 生产环境优先读取插件配置；本地容器允许用项目级环境变量注入，
		// 这样密钥不会进入 Git，也不会被写入 Agent 提示词或业务响应。
		$secret = trim((string)_get($this->plugin->options,'agentBridgeSecret',''));
		if(!$secret){$secret = trim((string)getenv('KOD_PROJECT_BRIDGE_SECRET'));}
		$ticket = (string)_get($_SERVER,'HTTP_X_KODAGENT_BRIDGE','');
		if(strlen($secret) < 32 || !$ticket){show_json('项目桥接服务未配置',false);}
		$parts = explode('.',$ticket,2);
		if(count($parts) !== 2){show_json('项目桥接票据无效',false);}
		$payload = $this->base64Decode($parts[0]);$signature = $this->base64Decode($parts[1]);
		if($payload === false || $signature === false || !hash_equals(hash_hmac('sha256',$parts[0],$secret,true),$signature)){show_json('项目桥接票据签名无效',false);}
		$claims = json_decode($payload,true);$now = time();
		if(!is_array($claims) || _get($claims,'purpose') !== 'project.read' || intval(_get($claims,'expiresAt',0)) <= $now || intval(_get($claims,'userId',0)) <= 0){show_json('项目桥接票据已过期或字段无效',false);}
		return $claims;
	}

	private function base64Decode($value){$value = strtr((string)$value,'-_','+/');$value .= str_repeat('=',(4 - strlen($value) % 4) % 4);return base64_decode($value,true);}
	private function json($data){show_json($data,true);}
}
