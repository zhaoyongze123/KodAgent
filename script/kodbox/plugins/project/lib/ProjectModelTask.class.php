<?php

/**
 * 项目-任务
 * 项目操作: 添加,编辑(name,desc,status); 归档/取消归档;删除/还原;彻底删除
 * status项目状态; 1=正常;2=已归档;0=已删除
 */
class ProjectModelTask extends ModelBase{
	protected $tableName = 'plugin_project_task';
	protected $tableMeta = array(
		"tableName"	=> 'plugin_project_task_meta',	//扩展名表名
		"metaField"	=> 'taskID'						//归类的字段名
	);
	protected $dataAuto = array(
		array('modifyTime','time','insert,update','function'), 	//插入或更新时自动添加 callback=当前类方法/function=全局函数;
		array('createTime','time','insert','function'), 		//插入时自定添加
		
		array('name','textEncode','insert,update','filter'),
		array('name','textDecode','select','filter'),
		array('desc','textEncode','insert,update','filter'),
		array('desc','textDecode','select','filter'),
	);
	
	const STATUS_DOING		= 1;	//正常
	const STATUS_ARCHIVED	= 2;	//已归档
	const STATUS_DELETED	= 0;	//已删除
	
	public $plugin;public $model;public $modelLog;public $modelUser;public $modelMeta;
	public function __construct($plugin){
		parent::__construct();

		$this->plugin 		= $plugin;
		$this->model 		= $this->plugin->model;
		$this->modelLog 	= $this->plugin->modelLog;
		$this->modelUser	= $this->plugin->modelUser;
		$this->modelMeta 	= Model($this->tableMeta['tableName']);
	}

	public $metaKeys = array(
		'tags', 		// 标签 '1,4,9'
		'taskCheck','taskLevel',
		'taskStatus','taskStatusBefore','taskFinishTime',	// 完成值,任务完成时间(自动更新);
		'userField_idxxx',	// 自定义字段; userField_[id],...
		'timeTo','timeMinute','timeFrom',	// 截止时间,显示分钟,开始时间;
		'attachment',// 附件;
		'styleCover','styleCoverFull','styleCoverColorDeep',// 风格样式
		'taskPercent','linkStartToStart','linkStartToEnd','linkEndToStart','linkEndToEnd',// 甘特图连接线;
		'timePlan','timeReal','timeDataAdd',// 计划工时,实际工时,工时添加记录
	);
	public $metaKeyJson = array('');
	
	private static $_listCache = array();
	private static $_listCacheSimple = array();	
	protected function getInfoSimple($id,$makeCache=false){
		$id = $id.'';
		if(isset(self::$_listCacheSimple[$id])){return self::$_listCacheSimple[$id];}
		$info = $this->where(array('taskID'=>$id))->find();
		self::$_listCacheSimple[$id] = $info;
		return $info;
	}
	protected function getInfo($id,$makeCache=false){
		$id = $id.'';
		if(isset(self::$_listCache[$id])){return self::$_listCache[$id];}
		$info  = $this->getInfoSimple($id);
		if(!$info) return false;
		$array = array($info);$this->_listDataApply($array);
		self::$_listCache[$id] = $array[0];
		return $array[0];
	}
	protected function _cacheRemove($id=false){
		$id = $id ? $id.'':'';
		if(!$id){
			self::$_listCacheSimple = array();
			self::$_listCache = array();return;
		}
		if(isset(self::$_listCacheSimple[$id])){unset(self::$_listCacheSimple[$id]);}
		if(isset(self::$_listCache[$id])){unset(self::$_listCache[$id]);}
	}
	
	protected function getInfoWithChildren($id){
		$taskInfo = $this->getInfo($id);
		$projectTask = $this->listProjectTask($taskInfo['projectID'],true);
		$taskInfoRes = $projectTask['listAll'][$id];
		if(!$taskInfoRes && $taskInfo){$taskInfoRes = $taskInfo;}
		return $taskInfoRes;
	}
	
	protected function dataAdd($data,$beforeTask=''){
		if(isset($data['sort']) && $data['sort']){
			$sortInfo = array('sort'=>$data['sort'],'change'=>array());
		}else{
			$sortInfo = $this->getSortInfo($data['projectID'],false,$data['pid'],$beforeTask);
		}
		if($data['isList'] == '1'){$data['pid'] = '0';}
		if($data['pid'] == '0'){$data['isList'] = '1';}
		if($data['projectID'] == '0'){
			$data['isList'] = '0';
			$data['ownerUser'] = USER_ID;
		}
		
		// 项目状态;1=正常;2=已归档;0=已删除; 设置了_status,则保持该状态;
		$status  = isset($data['_status']) ? $data['_status']:self::STATUS_DOING;
		$dataAdd = array(
			'projectID'		=> $data['projectID'],// 所在项目
			'pid'			=> $data['pid'],	// 父任务
			'name'			=> $data['name'],	// 名称
			'desc'			=> $data['desc'] ? $data['desc']:'',	// 描述
			'status'		=> $status,
			
			'isList'		=> $data['isList'],	// 是否为列表;
			'sort'			=> $sortInfo['sort'],// 排序;
			'ownerUser'		=> isset($data['ownerUser']) ? $data['ownerUser']:'', //任务负责人
			'createUser'	=> USER_ID,		 	// 创建者
			'modifyUser'	=> USER_ID,		 	// 最后修改者
		);
		$result = $this->add($dataAdd);
		$this->dataSetSortOthers($sortInfo['change']);
		
		$dataLog = $dataAdd;$dataLog['beforeTask'] = $beforeTask;
		$this->addLog($data['projectID'],$result,'task.add',$dataLog);
		return $result;
	}
	
	// 批量添加任务;默认添加到最后(或保持原顺序)
	public function dataAddMutil($taskArr,$projectTask,$option=array()){
		if(!is_array($taskArr) || !$taskArr || !$projectTask){return array();}
		$addArr = array();$addArrUser = array();$addArrMeta = array();$dataArrLog = array();
		$addMapAt    = array();$addResArr  = array();
		$metaKeys 	 = $this->metaKeysGet($projectTask['info']);
		$projectID   = $projectTask['info']['projectID'];
		$userAll 	 = $projectTask['info']['dataInfo']['userList'];
		$listAll 	 = $projectTask['listAll'];
		
		$modifyUser  = rand_from_to(500000000,900000000);// 随机数,用于批量插入后查询; 查询后重新更新;
		$sortMap = array('list'=> 0,'task'=>array());// taskChild parentTaskID => last;
		foreach($taskArr as $index => $data) {
			$dataAdd = array(
				'projectID'		=> $projectID,					// 所在项目
				'pid'			=> _get($data,'pid','0'),		// 父任务
				'name'			=> _get($data,'name',''),		// 名称
				'desc'			=> _get($data,'desc',''),		// 描述
				'status'		=> _get($data,'status',self::STATUS_DOING),
				
				'isList'		=> _get($data,'isList','0'),	// 是否为列表;
				'sort'			=> _get($data,'sort','0'),		// 排序; 默认添加到最后(序号处理)
				'ownerUser'		=> _get($data,'ownerUser',''), 	// 任务负责人
				'createUser'	=> USER_ID,		 	// 创建者
				'modifyUser'	=> USER_ID,		 	// 最后修改者
			);
			$dataAdd['modifyUser'] = $modifyUser;
			$pid = $dataAdd['pid'];
			if(isset($data['sort']) || _get($option,'keepSort') ) {
				$dataAdd['sort'] = intval($dataAdd['sort']);
			}else if($pid == '0'){
				if(!$sortMap['list']){
					$sortArr = array_to_keyvalue($projectTask['listGroup'],'','sort');$sortArr[] = count($sortArr);
					$sortMap['list'] = max($sortArr) + 1;
				}
				$dataAdd['sort'] = $sortMap['list']++;
			}else{
				if(!isset($sortMap['task'][$pid])){
					$parentChild = ($listAll[$pid] && is_array($listAll[$pid]['children'])) ? $listAll[$pid]['children']:array();
					$sortArr = array_to_keyvalue($parentChild,'','sort');$sortArr[] = count($sortArr);
					$sortMap['task'][$pid] = max($sortArr) + 1;
				}
				$dataAdd['sort'] = $sortMap['task'][$pid]++;
			}
			
			$addResArr[] = '';
			$parentTask  = ($dataAdd['pid'] == '0') ? true:$listAll[$pid];
			$desc = $dataAdd['desc'];
			if($desc){$desc = ModelBase::textEncode(Html::clean($desc));}
			if(!$parentTask || !$dataAdd['name'] || strlen($desc) > 60000){continue;}
			
			$ownerUser = $dataAdd['ownerUser'];
			if($ownerUser && !isset($userAll[$ownerUser]) ){$dataAdd['ownerUser'] = '';}
						
			$taskUser = array();
			if(isset($data['userHas'])){
				$users = $data['userHas'] ? explode(',',$data['userHas']):array();
				if(!$users){$users = array();}
				foreach($users as $userID){
					if(!isset($userAll[$userID])) continue;
					$taskUser[] = array('projectID' => $projectID,'taskID' => '','userID' => $userID,'authType' => 0);
				}
			}
			$taskMeta = array();
			if(is_array($data['metaInfo']) && $data['metaInfo']){
				foreach($data['metaInfo'] as $key=>$value){
					if(!in_array($key,$metaKeys)){continue;}
					if(strlen($value) >= 60000){continue;} //长度限制;
					$taskMeta[] = array('taskID' =>'','key' => $key,'value' => $value);
				}
			}
			
			$dataLog = $dataAdd;$dataLog['createUser'] = USER_ID;
			$dataArrLog[] = array(
				'projectID'	=> $projectID,	//项目id
				'taskID'	=> '',			//任务id
				'userID'	=> USER_ID,		//操作用户
				'logType'	=> 'task.add',
				'desc'		=> json_encode($dataLog),
			);
			$addArrUser[] = $taskUser;
			$addArrMeta[] = $taskMeta;
			$addArr[]     = $dataAdd;
			$addMapAt[]   = $index;
		}
		if(!$addArr){return array();}
		
		$this->addAll($addArr);
		$resultWhere = array('projectID'=>$projectID,'modifyUser'=>$modifyUser);
		$addResult = $this->field('taskID,name,pid,isList')->where($resultWhere)->select();
		$this->where($resultWhere)->save(array('modifyUser'=>USER_ID));
		
		// 刚插入的多个任务; 数量=$addArr=$addArrResult=$addArrMeta=$addArrUser;
		$dataUserHas = array();$dataMetaInfo = array();
		foreach($addResult as $i => $task){
			foreach($addArrUser[$i] as $v) {
				$v['taskID'] = $task['taskID'];
				$dataUserHas[] = $v;
			}
			foreach($addArrMeta[$i] as $v) {
				$v['taskID'] = $task['taskID'];
				$dataMetaInfo[] = $v;
			}
			$dataArrLog[$i]['taskID'] = $task['taskID'];
			$addResArr[$addMapAt[$i]] = $task;
		}
		
		// trace_log(['resAll'=>$addResArr,'res'=>$addResult,'add'=>$addArr,'userHas'=>$dataUserHas,'meta'=>$dataMetaInfo,'log'=>$dataArrLog]);
		if($dataUserHas){$this->modelUser->addAll($dataUserHas);}
		if($dataMetaInfo){$this->modelMeta->addAll($dataMetaInfo);}
		if($dataArrLog){$this->modelLog->addAll($dataArrLog);}
		$this->modelLog->lastID($projectID,'clear');
		return $addResArr;// [{taskID,name,pid,isList},'',{},...];//index和$taskArr一致;忽略的为空字符串;
	}
	
	// 批量添加任务(包含子任务; 列表--任务--子任务);
	public function dataAddMutilAndChild($taskArr,$projectID){
		if(!is_array($taskArr) || count($taskArr) == 0){return;}
		$addArr = array();
		$projectTask = $this->listProjectTask($projectID);
		$addTask = $this->_dataAddTaskLoop($taskArr,$projectTask,$addArr,0);
		// trace_log([101,$taskArr,$addTask]);
		return $addTask;
	}	
	private function _dataAddTaskLoop($taskArr,$projectTask,&$addArr,$deep){
		if(!is_array($taskArr) || count($taskArr) == 0 || $deep >= 50){return;}
		$taskArrNew = array();
		$addResArr  = $this->dataAddMutil($taskArr,$projectTask,array('keepSort'=>true));
		foreach($taskArr as $index => $task){
			$taskAddItem = $addResArr[$index];
			if(!$taskAddItem || !is_array($task['children']) || !$task['children']){continue;}
			$projectTask['listAll'][$taskAddItem['taskID']] = $taskAddItem;// 加入到listAll;
			foreach($task['children'] as $taskChild){
				$taskChild['pid'] = $taskAddItem['taskID'];
				$taskChild['isList'] = '0';
				$taskArrNew[] = $taskChild;
			}
		}
		$addArr[] = $taskArrNew;
		// trace_log([$deep,$taskArr,$addResArr,$taskArrNew]);
		$this->_dataAddTaskLoop($taskArrNew,$projectTask,$addArr,$deep++);
		return $addResArr;
	}	
	
	protected function dataEdit($id,$dataSet){
		$taskInfo 	= $this->getInfoSimple($id);
		$dataChange = array();$log = array();
		if(!$taskInfo) return false;
		foreach($dataSet as $key => $value){
			if($value == $taskInfo[$key]) continue;
			$dataChange[$key] = $value ? $value : '';
			$log[$key] = array($taskInfo[$key],$value);
		}
		if(!$dataChange) return true;
		
		$dataChange['modifyUser'] = USER_ID;
		$result = $this->where(array("taskID"=>$id))->save($dataChange);
		$this->addLog($taskInfo['projectID'],$id,'task.edit',$log);
		return $result;
	}
	protected function dataSetSort($id,$pid,$beforeTask,$addLog=true){
		$taskInfo 	= $this->getInfoSimple($id);
		if($taskInfo['isList'] == '1'){$pid = 0;}
		if($pid == $taskInfo['pid'] && $id == $beforeTask){return true;}
		$sortInfo 	= $this->getSortInfo($taskInfo['projectID'],$id,$pid,$beforeTask);
		if(!$sortInfo){return false;}
		
		$dataChange = array('pid'=>$pid,'sort'=>$sortInfo['sort']);
		$result = $this->where(array("taskID"=>$id))->save($dataChange);
		$this->dataSetSortOthers($sortInfo['change']);
		
		$pidTaskBefore = $taskInfo['pid'] ? $this->getInfoSimple($taskInfo['pid']):false;
		$pidTask = ($pid && $pid!= '0') ? $this->getInfoSimple($pid):false;
		$beforeTaskInfo = ($beforeTask && $beforeTask != '0') ? $this->getInfoSimple($beforeTask):false;
		$log = array(
			'pidFrom'		=> $taskInfo['pid'],'pidFromName' => $pidTaskBefore ? $pidTaskBefore['name']:'',
			'pidTo'			=> $pid,'pidToName'=>$pidTask ? $pidTask['name']:'',
			'beforeTask' 	=> $beforeTask,'beforeTaskName'=>$beforeTaskInfo ? $beforeTaskInfo['name']:'',
			'sort' 			=> $sortInfo['sort'],'sortTo'=>$sortInfo['change'],
		);
		if($addLog){$this->addLog($taskInfo['projectID'],$id,'task.setSort',$log);}
		return $result;
	}
	
	// 更新其他排序序号修改的任务;
	private function dataSetSortOthers($change){
		if(!is_array($change) || !count($change)) return;
		$saveData = array();
		foreach($change as $key => $sort){
			$saveData[] = array('taskID',$key,'sort',$sort);
		}
		$this->saveAll($saveData);
	}
	
	// 获取排序序号; 前后=从小到大; $id=0则代表新建; $pid=0代表新建列表; $beforeTask(前一个任务,空=最前面,'-'=最后面);
	// 列表新建拖拽[最前,x之后]; 任务新建[最前,中间,最后];任务拖拽[同列表最前,通列表x之后; 新列表x最前,新列表x之后];
	private function getSortInfo($projectID,$id,$pid,$beforeTask){
		$projectTask = $this->listProjectTask($projectID,true,true);
		$listAll 	= $projectTask['listAll'];
		// 列表排序;
		if(!$pid || $pid == 0){return $this->getSortWithList($projectTask['listGroup'],$id,$beforeTask);}

		// 新建任务;
		$parentList = is_array($listAll[$pid]['children']) ? $listAll[$pid]['children']: array();
		if(!$id || $id == 0){return $this->getSortWithList($parentList,$id,$beforeTask);}

		// 任务排序;
		$taskInfo  = $listAll[$id];
		$taskChild = $this->taskAllChild($taskInfo);
		if($pid == $taskInfo['taskID'] || $taskChild[$pid]){return false;} // 不能将任务移动到自己或自己的子任务下;		
		// trace_log([$taskInfo,$parentList,$taskChild]);
		return $this->getSortWithList($parentList,$id,$beforeTask);
	}
	
	private function taskAllChild($taskInfo,&$child=false){
		if(!$child){$child = array();}
		if(!$taskInfo || !is_array($taskInfo['children'])){return $child;}
		foreach($taskInfo['children'] as $item){
			if($child[$item['taskID']]){continue;}
			$child[$item['taskID']] = $item;
			$this->taskAllChild($item,$child);
		}
		return $child;
	}
	
	private function getSortWithList($listAll,$id,$beforeTask){
		$sort = array('sort'=>1,'change'=>array());//返回
		$isToFirst 	= (!$beforeTask || $beforeTask == '0') ? true:false;
		if(count($listAll) == 0){return $sort;} // 没有则放在第一位;
		if($isToFirst){
			if($listAll[0]['sort'] > 1){return $sort;} //有空位则直接加入;
			$sortFrom = $sort['sort'] + 1;
			foreach ($listAll as $item) {
				if($item['taskID'] == $id){continue;}
				if($item['sort'] != $sortFrom){$sort['change'][$item['taskID']] = $sortFrom;}
				$sortFrom++;
			}
			return $sort;
		}

		$sortFrom = $sort['sort']; $isFindBefore = false;
		foreach ($listAll as $item){
			if(!$isFindBefore){ // 直到找到前一个任务; 则后面任务都后移
				if($item['taskID'] != $beforeTask) continue;
				$isFindBefore = true;
				$sortFrom = intval($item['sort']) + 1;
				$sort['sort']  = $sortFrom++;
				continue;
			}
			if($item['taskID'] == $id){continue;}
			if($item['sort'] != $sortFrom){
				$sort['change'][$item['taskID']] = $sortFrom;
			}
			$sortFrom++;
		}
		if(!$isFindBefore){ // 没找到前面任务,则放在最后;
			$sort['sort']  = $sortFrom;
		}
		return $sort;
	}

	public function metaKeysGet($porjectInfo){
		$metaKeys 	 = $this->metaKeys;
		$userField   = $porjectInfo['metaInfo']['userField'];
		if(is_string($userField)){$userField = json_decode($userField,true);}
		$userField   = $userField ? $userField : array();
		foreach($userField as $field){
			$metaKeys[] = 'userField_'.$field['id']; // 追加自定义key;
			$metaKeys[] = 'userField_'.$field['id'].'_extra';// 附带扩展字段;
		}
		return $metaKeys;
	}
	
	protected function dataSetMeta($id,$metaData){
		$taskInfo = $this->getInfo($id);
		$dataChange = array();$log = array();
		foreach($metaData as $key => $value){
			//if(!in_array($key,$this->metaKeys)) continue;
			$valueBefore = $taskInfo['metaInfo'][$key];
			if(is_array($valueBefore)){$valueBefore = json_encode($valueBefore);}
			if(is_array($value)){$value = json_encode($value);}
			
			if(!$value && !$valueBefore) continue;
			if($value == $valueBefore) continue;
			$dataChange[$key] = $value ? $value : null;
			$log[$key] = array($valueBefore,$value);
		}
		if(!$dataChange) return true;
		$this->metaSet($id,$dataChange);
		$this->where(array("taskID"=>$id))->save(array('modifyTime'=>time()));
		$this->addLog($taskInfo['projectID'],$id,'task.metaSet',$log);
		return true;
	}
	protected function dataSetUser($id,$users){
		$taskInfo = $this->getInfo($id);
		$projectInfo = $this->plugin->model->getInfo($taskInfo['projectID']);
		$this->modelUser->where(array('taskID'=>$id))->delete();

		$userAll = $projectInfo['dataInfo']['userList'];
		$users   = $users ? explode(',',$users):array();
		$dataAdd = array();
		foreach ($users as $userID){
			if(!isset($userAll[$userID])) continue;
			$dataAdd[] = array(
				'projectID' => $projectInfo['projectID'],
				'taskID'	=> $id,
				'userID'	=> $userID,
				'authType'	=> 0,
			);
		}
		if($dataAdd){$this->modelUser->addAll($dataAdd);}
		
		$toUser = array_to_keyvalue($dataAdd,'','userID');
		$changeLog = array('from'=>$taskInfo['userHas'],'to'=>implode(',',$toUser));
		$this->addLog($taskInfo['projectID'],$id,'task.setUser',$changeLog);
		return true;
	}
	
	
	// 任务或列表移动; $pid=0 代表列表移动;  列表:本身及任务[及子任务]; 任务:本身及子任务;
	// 列表[目标项目,前一个任务id(分组序号,0=最前,空=最后)]; 任务[目标项目,分组,前一个任务id(0=最前,空=最后)]
	protected function taskMoveTo($id,$projectTo,$pid,$beforeTask){
		$taskInfo = $this->getInfoSimple($id);
		if(!$taskInfo){return false;}
		if($id == $beforeTask){return true;} // 位置不变;
		if($id == $pid){return true;} // 不能移动到自身;
		if($pid != '0'){
			$pidTask = $this->getInfoSimple($pid);
			if(!$pidTask || $pidTask['projectID'] != $projectTo){return false;}
		}
		
		if($taskInfo['projectID'] == $projectTo){ // 同项目;则处理为排序;
			$this->_changeStatus($id,self::STATUS_DOING);
			return $this->dataSetSort($id,$pid,$beforeTask);
		}

		// 获取所有子任务; 修改所属项目;
		$listChange  = array($taskInfo);// 列表:本身+任务(+子任务); 任务: 本身(+子任务)
		$projectTask = $this->listProjectTask($taskInfo['projectID']);
		$children    = _get($projectTask['listAll'][$taskInfo['taskID']],'children',array());
		foreach($children as $task){ // 最多两层;
			$listChange[] = $task;
			if(!is_array($task['children'])){continue;}
			foreach($task['children'] as $taskChildren){
				$listChange[] = $taskChildren;
			}
		}
		$arrayID  = array_to_keyvalue($listChange,'','taskID');
		$saveData = array('projectID'=>$projectTo);
		$this->where(array('taskID' => array('in',$arrayID)))->save($saveData);
		$this->modelLog->where(array('taskID' => array('in',$arrayID)))->save($saveData);
		$this->modelUser->where(array('taskID' => array('in',$arrayID)))->save($saveData);
		
		// 当前项目成员,目标项目中成员不存在时移除;
		$projectNew 	= $this->plugin->model->getInfo($projectTo);
		$projectUser 	= $projectTask['info']['dataInfo']['userList'];
		$projectUserNew = $projectNew['info']['dataInfo']['userList'];
		$newNotHave 	= array();
		foreach($projectUser as $userID => $user){
			if(!is_array($projectUserNew[$userID])){$newNotHave[] = $userID;}
		}
		if($newNotHave){
			$where = array(
				'projectID'	=> $projectTo,
				'userID'	=> array('in',$newNotHave),
				'taskID'	=> array('in',$arrayID)
			);
			$this->modelUser->where($where)->delete();
		}
		
		$beforeTaskInfo = ($beforeTask && $beforeTask != '0') ? $this->getInfoSimple($beforeTask):false;
		$changeLog = array(
			'projectFrom'	=> $taskInfo['projectID'],'projectFromName'=>$projectTask['info']['name'],
			'projectTo'		=> $projectTo,'projectToName'=>$projectNew['name'],
			'pidFrom' 		=> $taskInfo['pid'],'pidTo' => $pid,'pidToName'=>$pidTask ? $pidTask['name']:'',
			'beforeTask' 	=> $beforeTask,'beforeTaskName'=>$beforeTaskInfo ? $beforeTaskInfo['name']:'',
		);
		$this->_cacheRemove();
		$this->addLog($taskInfo['projectID'],$id,'task.moveOut',$changeLog);
		$this->addLog($projectTo,$id,'task.moveIn',$changeLog);
		$this->_changeStatus($id,self::STATUS_DOING);
		$this->dataSetSort($id,$pid,$beforeTask,false);//修改所属项目后重新排序;
		return true;
	}
	
	// 任务或列表复制; $pid=0 代表列表复制;
	// 列表[目标项目,前一个任务id(分组序号,0=最前,空=最后)]; 任务[目标项目,分组,前一个任务id(0=最前,空=最后)]
	public function taskCopyTo($id,$projectTo,$pid,$beforeTask,$options=array()){
		$taskInfo = $this->getInfoSimple($id);
		if(!$taskInfo){return false;}
		if($pid != '0'){
			$pidTask = $this->getInfoSimple($pid);
			if(!$pidTask || $pidTask['projectID'] != $projectTo){return false;}
		}
		
		$projectTask = $this->listProjectTask($taskInfo['projectID'],true);
		$taskNow = $projectTask['listAll'][$taskInfo['taskID']];
		if(!$taskNow){return false;}
		
		// 创建任务;创建任务meta; 保留任务指定成员(新项目中也包含该成员时);
		$projectNew  = $this->plugin->model->getInfo($projectTo);
		$porjectUser = $projectNew['dataInfo']['userList'];
		
		$options['_checkTaskStatus'] = $taskInfo['status'] == self::STATUS_DOING ? true:false; // 过滤正常状态任务;
		return $this->copyCreate($taskNow,$projectTo,$pid,$beforeTask,false,$porjectUser,$options);		
	}
	
	// 获取列表(本身+多个任务+任务子任务); 任务(本身+子任务);
	private function copyCreate($taskNow,$projectTo,$pid,$beforeTask,$keepSort=true,$porjectUser,$options){
		$taskNow['projectID'] = $projectTo;
		$taskNow['pid'] = $pid;
		if(!$keepSort){$taskNow['sort'] = false;}

		// 复制额外配置,默认不指定; 指定名称/忽略负责人及用户/忽略子任务; 自定义名称只使用一次;其他子任务不使用;
		if(isset($options['name']) && $options['name']){$taskNow['name'] = $options['name'];unset($options['name']);}
		if(isset($options['ignoreUserOwner'])){$taskNow['ownerUser'] = '';}
		if(isset($options['ignoreUserHas'])){$taskNow['userHas'] = '';}
		$createID = $this->dataAdd($taskNow,$beforeTask);
		if($taskNow['metaInfo']){
			$this->dataSetMeta($createID,$taskNow['metaInfo']);
		}
		if($taskNow['userHas']){
			$userSet = array();$userHas = explode(',',$taskNow['userHas']);
			foreach($userHas as $userID){
				if(is_array($porjectUser[$userID])){$userSet[] = $userID;}
			}
			if($userSet){$this->dataSetUser($createID,implode(',',$userSet));}
		}
		if(!is_array($taskNow['children'])) return $createID;
		
		$children = array();
		foreach($taskNow['children'] as $taskChildren){
			if($options['_checkTaskStatus'] && $taskChildren['status'] != self::STATUS_DOING){continue;}
			$taskChildren['pid'] = $createID;
			$children[] = $taskChildren;
		}
		$this->dataAddMutilAndChild($children,$projectTo);//批量复制子任务;
		return $createID;
	}
	
	public function listData($projectID,$allStatus=0){
		$result = $this->listProjectTask($projectID,$allStatus);
		return $result['listGroup'];
	}
	public function listTaskAll($projectID,$isAdmin){
		return $this->listTaskAllForUser($projectID,$isAdmin,USER_ID);
	}

	/**
	 * 按指定 KodCloud 用户读取项目任务。
	 *
	 * 参数：
	 * - $projectID：项目编号。
	 * - $isAdmin：是否为项目管理员；管理员可看全部任务。
	 * - $userID：需要套用任务隐私规则的用户编号。
	 *
	 * Agent 桥接层不能伪造 PHP 全局 USER_ID，因此 UI 与 Agent 共用这段
	 * 过滤逻辑，避免 taskShowOnlySelf 在两条链路上出现不同结果。
	 */
	public function listTaskAllForUser($projectID,$isAdmin,$userID,$initializeFolder=true){
		$project = $this->model->getInfo($projectID);
		if(!$project){return false;}
		
		// 页面读取继续保留插件原有的资料目录初始化行为；Agent 只读桥接层
		// 传入 false，避免查询项目任务时偷偷创建目录或写入项目元数据。
		if($initializeFolder){ProjectModelFile::projectCheckFolder($this->model,$project);}
		$taskList = $this->listData($projectID,1);
		$result   = array('project'=>$project,'taskList'=>$taskList);
		$showOnlySelf = _get($project,'metaInfo.taskShowOnlySelf','0');
		if($isAdmin || $showOnlySelf != '1'){return $result;}
		// 任务隐私必须递归应用到所有层级。旧逻辑只过滤列表的第一层，
		// 深层子任务会在 Agent/报告链路中泄露给普通成员。
		$taskList = $this->filterTaskTreeForUser($taskList,$userID,$project);
		
		$result['taskList'] = $taskList;
		return $result;
	}

	/** 递归保留本人负责、参与、创建的任务及其必要的父级容器。 */
	private function filterTaskTreeForUser($items,$userID,$project){
		$result = array();
		foreach((array)$items as $task){
			if(!is_array($task)){continue;}
			$children = $this->filterTaskTreeForUser(_get($task,'children',array()),$userID,$project);
			$ownAllowed = $this->taskSelfAllow($task,$userID) === true;
			if(!$ownAllowed && !$children){continue;}
			$task['children'] = $children;
			$task['childrenNum'] = count($children);
			$task['childrenChecked'] = 0;
			foreach($children as $child){
				if($this->taskFinished($child,$project)){$task['childrenChecked']++;}
			}
			$result[] = $task;
		}
		return $result;
	}
	
	
	public function listProjectTask($projectID,$allStatus=0,$isSimple=false){
		$where = array('projectID'=>$projectID,'status'=>self::STATUS_DOING);
		if($allStatus){unset($where['status']);}
		
		$projectInfo = $this->model->getInfo($projectID);
		$field = $isSimple ? 'taskID,name,pid,sort,status':'*';		
		$list  = $this->field($field)->where($where)->select();
		if(!$list){$list = array();}
		
		if(!$isSimple){
			$this->_listDataApply($list);
			foreach($list as $item){
				self::$_listCacheSimple[$item['taskID'].''] = $item;
				self::$_listCache[$item['taskID'].''] = $item;
			}
		}
		
		$listTask  = array_to_keyvalue($list,'taskID');
		$listGroup = array();$listAll = array();
		foreach($listTask as &$task){
			if(!$task){return;}
			$pid = $task['pid'];
			$listAll[$task['taskID']] = &$task;
			if(!$pid || $pid=='0'){$listGroup[] = &$task;continue;}
			if(!isset($listTask[$pid])){
				continue;// 未知任务;归类处理;  暂时忽略;
				$pid = '-';
				if(!is_array($listTask[$pid])){
					$name = LNG('project.import.listDefault');
					$listTask[$pid] = array('taskID'=>'-','isList'=>'1','pid'=>'0','status'=>'1','name'=>$name);
				}
			}

			$taskParent = &$listTask[$pid];
			if(!isset($taskParent['children'])){$taskParent['children'] = array();}
			if(!isset($taskParent['childrenNum'])){
				$taskParent['childrenNum'] = 0;
				$taskParent['childrenChecked'] = 0;
			}
			if(is_array($task['metaInfo']) && $task['status'] == $taskParent['status']){
				$taskParent['childrenNum'] += 1;
				if($this->taskFinished($task,$projectInfo)){$taskParent['childrenChecked'] += 1;}
			}
			$taskParent['children'][] = &$task;
		};unset($task);
		$listGroup = $this->listDataSort($listGroup);
		return array('listAll'=>$listAll,'listGroup'=>$listGroup,'info'=>$projectInfo);
	}
	
	public function taskSelfAllow($task,$userID = false){
		$userID = $userID === false ? USER_ID : $userID;
		if( $task['ownerUser']  == $userID ||
			$task['createUser'] == $userID ||
			strstr(','.$task['userHas'].',',','.$userID.',')
		){return true;}
	}
	
	// 任务是否完成;
	public function taskFinished($task,$projectInfo){
		// return $task['metaInfo']['taskCheck'] == '1';
		$dataType = _get($projectInfo,'metaInfo.taskFinishType','taskCheck');
		$meta = $task['metaInfo'] ? $task['metaInfo'] : array();
		if($dataType == 'taskNone'){return false;}
		if($dataType == 'taskCheck'  && $meta['taskCheck'] == '1'){return true;}
		if($dataType == 'taskStatus' && $meta['taskStatus'] == 'finished'){return true;}
		if($dataType == 'taskBug' && $meta['taskStatus'] == 'closed'){return true;}
		if($dataType == 'taskDiy'){
			$listArr = _get($projectInfo,'metaInfo.taskFinishDiy',array());
			if(!$listArr || !is_array($listArr[0])){return false;}
			$find = array_find_by_field($listArr,'type','finished');
			if(!$find){$find = $listArr[count($listArr) - 1];}
			if($find && $find['id'] && $find['id'] == $meta['taskStatus']){return true;}
		}		
	}
	
	public function listTasks($projectID,$taskArr){
		if(!$taskArr){return array();}
		$taskArr = array_unique($taskArr);
		$where = array('projectID'=>$projectID,'taskID'=>array('in',$taskArr));
		$list  = $this->where($where)->select();
		$this->_listDataApply($list);
		return $list;
	}
	
	public function listTasksSimple($idArray){
		$idArray = array_unique($idArray);
		if(!$idArray){return array();}
		
		$where = array('taskID'=>array('in',$idArray));
		$list  = $this->where($where)->select();
		$this->_listAppendMeta($list,$idArray);
		return array_to_keyvalue($list,'taskID');
	}

	// 排序处理; 分栏排序;任务卡片排序;子任务排序;
	private function listDataSort(&$listResult,$deep=0){
		$listResult = array_sort_by($listResult,'sort',false,'taskID');
		if($deep >= 50){return $listResult;}
		foreach ($listResult as $key => $task){
			if(!is_array($task['children'])) continue;
			$listResult[$key]['children'] = $this->listDataSort($listResult[$key]['children'],$deep++);
		}
		return $listResult;
	}
	
	public function _listDataApply(&$list){
		if(!$list) return;
		$idArray = array_to_keyvalue($list,'','taskID');
		$this->_listAppendMeta($list,$idArray);
		$this->_listAppendUser($list,$idArray);
		$this->_listAppendCommentCount($list,$idArray);
	}
	
	protected function _listAppendUser(&$list,$idArray){
		$where 	 	 = array('taskID'=>array('in',$idArray));
		$userAll 	 = $this->modelUser->where($where)->select();
		$userProject = array_to_keyvalue_group($userAll,'taskID');
		$userOwner   = array_to_keyvalue($list,'','ownerUser');
		$userCreate  = array_to_keyvalue($list,'','createUser');
		$userModify  = array_to_keyvalue($list,'','modifyUser');
		$userIdArr 	 = array_merge(array_to_keyvalue($userAll,'','userID'),$userCreate,$userModify,$userOwner);		
		$userListInfo= Model('User')->userListInfo($userIdArr);

		foreach ($list as &$item) {
			$taskUser = _get($userProject,$item['taskID'],array());
			$item['userHas'] 		= trim(implode(',',array_to_keyvalue($taskUser,'','userID')),',');
			$item['createUserInfo'] = _get($userListInfo,$item['createUser'],false);
			$item['modifyUserInfo'] = _get($userListInfo,$item['modifyUser'],false);
			if(!$item['ownerUser'] || $item['ownerUser'] == '0'){$item['ownerUser'] = '';}
		};unset($item);
	}
	
	protected function _listAppendMeta(&$list,$idArray){
		$where = array("taskID" => array("in",$idArray));
		$meta  = $this->modelMeta->field("taskID,key,value")->where($where)->select();
		$metaArray = array_to_keyvalue_group($meta,'taskID');
		foreach ($list as &$item) {
			$item['metaInfo'] = array();
			if(!isset($metaArray[$item['taskID']])) continue;
			foreach( $metaArray[$item['taskID']] as $kv){
				if(in_array($kv['key'],$this->metaKeyJson)){
					$kv['value'] = json_decode($kv['value'],true);
				}
				$item['metaInfo'][$kv['key']] = $kv['value'];
			}
		};unset($item);
	}
	protected function _listAppendCommentCount(&$list,$idArray){
		$targetType = ProjectModel::COMMENT_TYPE_PROJECT_TASK;
		$commentCountArr = Model('Comment')->commentCount($idArray,$targetType);
		// $starCountArr = Model('Comment')->starTargetCount($idArray,$targetType);
		foreach ($list as &$item){
			$item['commentInfo'] = array(
				'commentCount' 	=> _get($commentCountArr,$item['taskID'],0),
				// 'starCount' 	=> _get($starCountArr['allCount'],$item['taskID'],0),
				// 'starSelf' 	=> _get($starCountArr['selfCount'],$item['taskID'],0),
			);
		};unset($item);
	}
	
	
	protected function taskRemove($id){return $this->_changeStatus($id,self::STATUS_DELETED,'task.remove');}
	protected function taskArchive($id){return $this->_changeStatus($id,self::STATUS_ARCHIVED,'task.archive');}
	protected function taskRemoveCancel($id){return $this->_changeStatus($id,self::STATUS_DOING,'task.removeCancel');}
	protected function taskArchiveCancel($id){return $this->_changeStatus($id,self::STATUS_DOING,'task.archiveCancel');}
	
	// 移动任务/列表修改状态(将所有任务子任务都处理为该状态; 如果当前就是该状态则不处理)
	protected function _changeStatus($id,$status,$logType=''){
		$dataInfo = $this->getInfoSimple($id);
		if(!$dataInfo || $dataInfo['status'] == $status) return false;
		$taskItem  = $this->getInfoAllChildren($id);
		if(!$taskItem['info'] || !$taskItem['arr']){return false;}
		
		$this->where(array("taskID"=>array('in',$taskItem['arr'])))->save(array('status'=>$status));
		if($logType){
			$this->addLog($dataInfo['projectID'],$id,$logType,array('status'=>$status));
		}
		return true;
	}
	
	public function addLog($projectID,$taskID,$logType,$data=array()){
		$dataInfo = $this->getInfoSimple($taskID);
		$data['taskName'] = $dataInfo['name'];
		$data['isList']   = $dataInfo['isList'];
		$this->modelLog->addLog($projectID,$taskID,$logType,$data);
		if($dataInfo['modifyUser'] != USER_ID){ // 添加或编辑本身已经带入,不更新最后修改者;
			$this->where(array("taskID"=>$taskID))->save(array('modifyUser'=>USER_ID));
		}
		$this->_cacheRemove($taskID);
	}
	
	// 获取任务所有子任务(包含任务自身id); 子任务;任务/子任务;列表/任务/子任务;
	private function getInfoAllChildren($id){
		$taskInfo = $this->getInfoSimple($id);
		$result   = array('info'=>$taskInfo,'arr'=>array());
		if(!$taskInfo){return $result;}
		
		$projectTask = $this->listProjectTask($taskInfo['projectID'],true,true);
		$taskChild = $this->taskAllChild($projectTask['listAll'][$id]);
		$result['arr'] = array_keys($taskChild);
		$result['arr'][] = $id;
		return $result;
	}

	// 彻底删除任务,及子任务;
	protected function taskRemoveForce($id){
		$taskItem = $this->getInfoAllChildren($id);
		if(!$taskItem['info'] || !$taskItem['arr']){return false;}

		$where = array("taskID"=>array('in',$taskItem['arr']));
		$this->where($where)->delete();
		$this->modelLog->where($where)->delete();
		$this->modelUser->where($where)->delete();
		$this->modelMeta->where($where)->delete();
		Model("Comment")->removeTarget(ProjectModel::COMMENT_TYPE_PROJECT_TASK,$taskItem['arr']);
		
		$taskInfo = $taskItem['info'];
		$logData  = array('taskName'=>$taskInfo['name'],'taskID'=>$id,'isList'=>$taskInfo['isList']);
		$this->modelLog->addLog($taskInfo['projectID'],$id,'task.removeForce',$logData);
	}
}
