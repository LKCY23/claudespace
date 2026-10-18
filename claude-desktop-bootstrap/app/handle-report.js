// Consume the public claude-config report. Never read or merge native settings.
ObjC.import('Foundation');
ObjC.import('stdlib');

function reportLocation(report) {
    const artifacts = report.artifacts || {};
    return artifacts.saved && typeof artifacts.json_path === 'string'
        ? '\n完整 JSON：' + artifacts.json_path : '';
}

function failure(message, report) {
    throw new Error(message + (report ? reportLocation(report) : ''));
}

// Render only the five supported Desktop preferences from the framework report.
// This is a display mapping, not another settings reader or merge policy.
const preferenceNames = {
    chatTabEnabled: 'Chat 入口', autoModeEnabled: 'Auto 模式',
    builtinBrowserEnabled: '内置浏览器', userThemeMode: '主题', locale: '界面语言'
};

function preferenceValue(row, side) {
    if (row[side + '_exists'] === false) return '未设置';
    const value = row[side];
    if (typeof value === 'boolean') return value ? '开启' : '关闭';
    if (typeof value !== 'string') return '详见报告';
    if (row.path[1] === 'userThemeMode') {
        return {system: '跟随系统', light: '浅色', dark: '深色'}[value] || '详见报告';
    }
    return row.path[1] === 'locale' && /^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/.test(value)
        ? value : '详见报告';
}

function preferenceSummary(report, applied) {
    const lines = [];
    for (const row of report.decisions || []) {
        if (!Array.isArray(row.path) || row.path.length !== 2 || row.path[0] !== 'settings'
            || !Object.prototype.hasOwnProperty.call(preferenceNames, row.path[1])) continue;
        let status;
        if (row.action === 'unchanged') status = '已一致';
        else if (row.action === 'add') status = applied ? '已新增' : '待新增';
        else if (row.action === 'overwrite') status = applied ? '已更新' : '待更新';
        else if (row.action === 'preserve') status = '按策略保留本机值';
        else if (row.action === 'residual') status = 'Profile 已移除声明，本机值保留';
        else if (row.action === 'conflict') status = '有冲突，未修改';
        else status = '处理方式详见报告';
        const before = preferenceValue(row, 'before');
        const value = ['add', 'overwrite'].includes(row.action)
            ? before + ' → ' + preferenceValue(row, 'after') : before;
        let line = preferenceNames[row.path[1]] + '：' + value + '（' + status + '）';
        if (['preserve', 'conflict'].includes(row.action) && row.incoming_exists === true) {
            line += '；Profile 要求：' + preferenceValue(row, 'incoming');
        }
        lines.push(line);
    }
    return lines.length ? '\n' + lines.join('\n') : '\n报告未列出可展示的偏好明细，请查看完整 JSON。';
}

function readReport(path, exitCode, operation, machineFile) {
    let report;
    try {
        const text = $.NSString.stringWithContentsOfFileEncodingError($(path), $.NSUTF8StringEncoding, null);
        report = JSON.parse(ObjC.unwrap(text));
    } catch (error) {
        failure('claude-config 未返回有效 JSON；请查看本次原始输出。');
    }
    if (!report || report.schema_version !== 1) failure('不支持此报告格式，请更新 claude-config。');
    if (exitCode !== '0' || report.status !== 'ok' || report.ready !== true || (report.errors || []).length) {
        const issues = (report.errors || []).concat(report.blockers || []);
        let reason = issues.length ? (issues[0].reason || issues[0].code) : '配置检查或应用未完成。';
        if (issues.some(issue => issue.code === 'app_running')) reason = '本次需要写入偏好，但 Claude 仍在运行。请保存工作并用 ⌘Q 正常退出，再点击启动器；不会自动强退应用。';
        if (issues.some(issue => issue.name === 'claude_deployment_scope')) reason = '当前绑定不是已配置好的第三方部署；不会切换部署模式。';
        failure('未启动 Claude：' + reason + (operation === 'plan' ? preferenceSummary(report, false) : ''), report);
    }
    if (report.operation !== operation) failure('配置工具返回了不同的操作结果，已停止启动。', report);
    const target = report.targets && report.targets.length === 1 ? report.targets[0] : null;
    if (!target || target.app !== 'claude-desktop' || typeof target.application !== 'string'
        || !target.application.startsWith('/') || !target.application.endsWith('.app')
        || typeof target.data_root !== 'string' || !target.data_root.startsWith('/')
        || typeof target.machine_file !== 'string' || !target.machine_file.startsWith('/')
        || target.machine_file !== machineFile
        || typeof target.profile !== 'string' || !target.profile.trim()) {
        failure('报告缺少明确的 Claude 启动绑定；请使用支持 Bootstrap 的 claude-config 0.1.4 或更新版本。', report);
    }
    if (target.deployment_mode !== '3p') {
        failure('此启动器用于已配置好的第三方 Claude Desktop。当前绑定不是第三方部署，已停止；不会切换部署模式。', report);
    }
    if (target.data_root !== target.default_third_party_data_root) {
        failure('Machine 绑定的数据目录不是 Claude 原生的第三方目录；普通启动无法选择自定义数据目录，已停止。', report);
    }
    if (!report.artifacts || report.artifacts.saved !== true) failure('完整报告未保存，已停止启动。', report);
    return report;
}

function openDesktop(application, report) {
    const task = $.NSTask.alloc.init;
    task.launchPath = '/usr/bin/open';
    task.arguments = ['-a', application];
    try {
        task.launch;
        task.waitUntilExit;
        if (task.terminationStatus !== 0) failure('配置已应用，但 macOS 未能打开 Claude。', report);
    } catch (error) {
        failure('配置已应用，但 macOS 未能打开 Claude。', report);
    }
}

function run(args) {
    try {
        const mode = args[0];
        if (!['check', 'preview', 'launch'].includes(mode)) failure('无效的启动器操作。');
        const plan = readReport(args[1], args[2], 'plan', args[3]);
        if (!/^[0-9a-f]{64}$/.test(plan.plan_id || '')) failure('报告没有可校验的计划标识。', plan);
        if (mode === 'check') return plan.plan_id;
        if (mode === 'preview') return 'Claude Bootstrap · 配置预览\n' + plan.summary.changes
            + ' 项配置差异；未应用配置、未启动 Claude。' + preferenceSummary(plan, false) + reportLocation(plan);
        const applied = readReport(args[4], args[5], 'apply', args[3]);
        const before = plan.targets[0], after = applied.targets[0];
        for (const key of ['machine_file', 'profile', 'application', 'data_root', 'deployment_mode', 'default_third_party_data_root']) {
            if (before[key] !== after[key]) failure('检查与应用的目标绑定不一致，已停止启动。', applied);
        }
        if (applied.plan_id !== plan.plan_id || applied.preview_only !== false
            || !applied.execution || !['completed', 'unchanged'].includes(applied.execution.status)
            || applied.execution.started !== true) {
            failure('配置计划未完整执行，已停止启动。', applied);
        }
        openDesktop(after.application, applied);
        return 'Claude Bootstrap · 第三方 Desktop\n'
            + (applied.execution.status === 'unchanged' ? '配置无需修改，已请求启动 Claude。' : '配置已应用，已请求启动 Claude。')
            + preferenceSummary(applied, true)
            + '\n界面实际生效尚未验证；本工具不检查网络或切换供应商。' + reportLocation(applied);
    } catch (error) {
        $.NSFileHandle.fileHandleWithStandardError.writeData($(String(error.message) + '\n').dataUsingEncoding($.NSUTF8StringEncoding));
        $.exit(1);
    }
}
