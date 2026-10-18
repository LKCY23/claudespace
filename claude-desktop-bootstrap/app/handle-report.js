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
        if (issues.some(issue => issue.code === 'app_running')) reason = '请保存工作并用 ⌘Q 正常退出 Claude，再点击启动器；不会自动强退应用。';
        if (issues.some(issue => issue.name === 'claude_deployment_scope')) reason = '当前绑定不是已配置好的第三方部署；不会切换部署模式。';
        failure('未启动 Claude：' + reason, report);
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
        if (mode === 'preview') return '预览通过：' + plan.summary.changes + ' 项配置差异；未应用配置、未启动 Claude。' + reportLocation(plan);
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
        return '配置已就绪，已请求启动 Claude。' + reportLocation(applied);
    } catch (error) {
        $.NSFileHandle.fileHandleWithStandardError.writeData($(String(error.message) + '\n').dataUsingEncoding($.NSUTF8StringEncoding));
        $.exit(1);
    }
}
