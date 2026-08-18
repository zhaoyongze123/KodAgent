kodReady.push(function(){
    var pageId = '{{package.id}}';
    var pageTitle = '{{package.name}}';
    var pluginUrl = '/index.php?plugin/approvalCreateCenter/index';
    function buildFreshUrl(){ return pluginUrl + '&_pluginRefresh=' + Date.now(); }
    Events.bind('main.menu.loadBefore', function(listData){
        listData[pageId] = {name: pageTitle, url: pluginUrl, target: '{{config.openWith}}',
            subMenu: '{{config.menuSubMenu}}', menuAdd: '{{config.menuAdd}}', icon: 'ri-draft-fill'};
    });
    Router.mapIframe({page: pageId, title: pageTitle, url: buildFreshUrl(), ignoreLogin: false});
});
