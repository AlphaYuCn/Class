/* 班级管理系统 - ECharts 通用封装
 * 全局函数:
 *   initHistogram(examId) - 渲染班级分数分布直方图(支持柱体点击跳转个人)
 *   initSubjectBar(examId) - 渲染各科平均分对比条形图
 *   initRadar(examId, studentId) - 渲染九科雷达图(个人 vs 班均)
 * 点击直方图柱体或雷达 legend 跳转个人下钻页
 */
(function () {
  // 颜色常量
  const COLORS = {
    bar: '#4e79a7',
    avg: '#59a14f',
    max: '#e15759',
    min: '#f28e2b',
    personal: '#e15759',
    classAvg: '#4e79a7',
  };

  function api(path) {
    return path;  // 已经是绝对路径
  }

  function fetchJSON(url) {
    return fetch(url).then(r => {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  // 成绩格式化: 保留1位小数
  function fmt1(v) { return v != null && v !== '' ? Number(v).toFixed(1) : ''; }

  // 直方图
  window.initHistogram = function (examId) {
    const el = document.getElementById('histogram');
    if (!el || typeof echarts === 'undefined') return;
    const chart = echarts.init(el);
    const hint = document.getElementById('histogram-hint');
    chart.showLoading('default', { text: '加载中...', color: '#4e79a7' });
    fetchJSON(`/scores/api/exam/${examId}/histogram`)
      .then(data => {
        chart.hideLoading();
        const max = Math.max(...data.counts, 1);
        chart.setOption({
          tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            formatter: function (params) {
              const idx = params[0].dataIndex;
              const seg = data.segments[idx];
              return `${seg.range}<br/>${seg.count} 人 (${seg.start}-${seg.end})`;
            }
          },
          grid: { left: 40, right: 20, top: 30, bottom: 40 },
          xAxis: {
            type: 'category',
            data: data.categories,
            axisLabel: { rotate: 45, fontSize: 10 },
            name: '分数段'
          },
          yAxis: { type: 'value', name: '人数', minInterval: 1 },
          series: [{
            name: '人数',
            type: 'bar',
            data: data.counts.map((v, i) => ({
              value: v,
              itemStyle: { color: v ? COLORS.bar : '#ccc' }
            })),
            barMaxWidth: 40,
            label: { show: true, position: 'top' }
          }]
        });
        // 点击柱体跳转该分数段第一名 (近似)
        chart.on('click', function (params) {
          const seg = data.segments[params.dataIndex];
          if (seg && seg.count > 0) {
            // 跳转回 overview 页对应锚点，无具体学生 id
            window.location.href = `/scores/exam/${examId}#students`;
          }
        });
        if (hint) hint.textContent = `共 ${data.segments.length} 档`;
      })
      .catch(err => {
        chart.hideLoading();
        chart.setOption({
          title: { text: '加载失败', left: 'center', top: 'center',
                   textStyle: { color: '#dc3545', fontSize: 14 } }
        });
        if (hint) hint.textContent = err.message;
      });
    window.addEventListener('resize', () => chart.resize());
  };

  // 各科平均分条形图
  window.initSubjectBar = function (examId) {
    const el = document.getElementById('subject-bar');
    if (!el || typeof echarts === 'undefined') return;
    const chart = echarts.init(el);
    const hint = document.getElementById('subject-bar-hint');
    chart.showLoading('default', { text: '加载中...', color: COLORS.avg });
    fetchJSON(`/scores/api/exam/${examId}/subject-bar`)
      .then(data => {
        chart.hideLoading();
        chart.setOption({
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
            valueFormatter: v => v != null ? Number(v).toFixed(1) : '-' },
          legend: { data: ['平均分', '最高分', '最低分'], top: 0 },
          grid: { left: 40, right: 20, top: 40, bottom: 60 },
          xAxis: {
            type: 'category',
            data: data.categories,
            axisLabel: { rotate: 30, fontSize: 11 }
          },
          yAxis: { type: 'value', name: '分数' },
          series: [
            {
              name: '平均分', type: 'bar', data: data.avg,
              itemStyle: { color: COLORS.avg }, barMaxWidth: 30,
              label: { show: true, position: 'top', fontSize: 10,
                       formatter: p => p.value != null ? Number(p.value).toFixed(1) : '' }
            },
            {
              name: '最高分', type: 'line', data: data.max,
              itemStyle: { color: COLORS.max }, symbol: 'circle', symbolSize: 6
            },
            {
              name: '最低分', type: 'line', data: data.min,
              itemStyle: { color: COLORS.min }, symbol: 'rect', symbolSize: 6
            },
          ]
        });
        if (hint) hint.textContent = '条形=平均分 / 折线=最高/最低';
      })
      .catch(err => {
        chart.hideLoading();
        chart.setOption({
          title: { text: '加载失败', left: 'center', top: 'center',
                   textStyle: { color: '#dc3545', fontSize: 14 } }
        });
        if (hint) hint.textContent = err.message;
      });
    window.addEventListener('resize', () => chart.resize());
  };

  // 个人雷达图(本次个人 vs 班均)
  window.initRadar = function (examId, studentId) {
    const el = document.getElementById('radar');
    if (!el || typeof echarts === 'undefined') return;
    const chart = echarts.init(el);
    const hint = document.getElementById('radar-hint');
    chart.showLoading('default', { text: '加载中...', color: COLORS.personal });
    fetchJSON(`/scores/api/exam/${examId}/student/${studentId}/radar`)
      .then(data => {
        chart.hideLoading();
        chart.setOption({
          tooltip: { trigger: 'item',
            valueFormatter: v => v != null ? Number(v).toFixed(1) : '-' },
          legend: { data: ['个人', '班均'], top: 0 },
          radar: {
            indicator: data.indicators,
            shape: 'polygon',
            splitNumber: 5,
            axisName: { color: '#666', fontSize: 11 }
          },
          series: [{
            type: 'radar',
            data: [
              {
                name: '个人',
                value: data.personal,
                itemStyle: { color: COLORS.personal },
                areaStyle: { color: 'rgba(225,87,89,0.2)' }
              },
              {
                name: '班均',
                value: data.avg,
                itemStyle: { color: COLORS.classAvg },
                areaStyle: { color: 'rgba(78,121,167,0.15)' }
              }
            ]
          }]
        });
        if (hint) hint.textContent = `学生: ${data.studentName}`;
      })
      .catch(err => {
        chart.hideLoading();
        chart.setOption({
          title: { text: '加载失败', left: 'center', top: 'center',
                   textStyle: { color: '#dc3545', fontSize: 14 } }
        });
        if (hint) hint.textContent = err.message;
      });
    window.addEventListener('resize', () => chart.resize());
  };

  // 学生成绩趋势(总分+班排 主图 + 九科副图)
  window.initTrend = function (studentId) {
    const totalEl = document.getElementById('trend-total');
    const subjEl = document.getElementById('trend-subjects');
    if (typeof echarts === 'undefined') return;

    fetchJSON(`/scores/api/trend/${studentId}`)
      .then(data => {
        if (!data.exams || !data.exams.length) return;
        const examLabels = data.exams.map(e => e.name);
        // 主图: 总分 + 班排(双轴)
        if (totalEl) {
          const c1 = echarts.init(totalEl);
          const totalSeries = data.series.find(s => s.name === '总分');
          const rankSeries = data.series.find(s => s.name === '班级排名');
          c1.setOption({
            tooltip: { trigger: 'axis',
              formatter: function (params) {
                let s = params[0].axisValue + '<br/>';
                params.forEach(p => {
                  const v = p.value;
                  const fmt = (p.seriesName === '总分' && v != null) ? Number(v).toFixed(1) : (v != null ? v : '-');
                  s += p.marker + p.seriesName + ': ' + fmt + '<br/>';
                });
                return s;
              }
            },
            legend: { data: ['总分', '班级排名'], top: 0 },
            grid: { left: 50, right: 50, top: 40, bottom: 60 },
            xAxis: { type: 'category', data: examLabels,
                     axisLabel: { rotate: 20 } },
            yAxis: [
              { type: 'value', name: '总分', position: 'left' },
              { type: 'value', name: '班排(越小越好)', position: 'right',
                inverse: true, minInterval: 1 }
            ],
            series: [
              { name: '总分', type: 'line', yAxisIndex: 0,
                data: totalSeries.data, smooth: true,
                itemStyle: { color: COLORS.bar },
                label: { show: true,
                         formatter: p => p.value != null ? Number(p.value).toFixed(1) : '' } },
              { name: '班级排名', type: 'line', yAxisIndex: 1,
                data: rankSeries.data, smooth: true,
                itemStyle: { color: COLORS.personal } }
            ]
          });
          window.addEventListener('resize', () => c1.resize());
        }
        // 副图: 九科趋势
        if (subjEl) {
          const c2 = echarts.init(subjEl);
          const subjectSeries = data.series.filter(s =>
            s.name !== '总分' && s.name !== '班级排名');
          c2.setOption({
            tooltip: { trigger: 'axis' },
            legend: { type: 'scroll', top: 0,
                      data: subjectSeries.map(s => s.name) },
            grid: { left: 40, right: 20, top: 40, bottom: 60 },
            xAxis: { type: 'category', data: examLabels,
                     axisLabel: { rotate: 20 } },
            yAxis: { type: 'value', name: '分数' },
            series: subjectSeries.map((s, i) => ({
              name: s.name, type: 'line', data: s.data, smooth: true,
              connectNulls: true,
              lineStyle: { width: 1.5 }
            }))
          });
          window.addEventListener('resize', () => c2.resize());
        }
      })
      .catch(err => {
        if (totalEl) {
          const c = echarts.init(totalEl);
          c.setOption({ title: { text: '加载失败: ' + err.message,
                                  left: 'center', top: 'center',
                                  textStyle: { color: '#dc3545', fontSize: 14 } } });
        }
      });
  };

  // 班级进步/退步榜
  window.initRanking = function (examId) {
    const progressTbody = document.querySelector('#progress-table tbody');
    const regressTbody = document.querySelector('#regress-table tbody');
    const allTbody = document.querySelector('#all-table tbody');
    const meta = document.getElementById('ranking-meta');
    const url = '/scores/api/ranking' + (examId ? `?eid=${examId}` : '');
    fetchJSON(url)
      .then(data => {
        // 渲染进步榜
        if (progressTbody) {
          progressTbody.innerHTML = data.progress.length
            ? data.progress.map((p, i) => `
              <tr>
                <td><span class="badge bg-success">${i+1}</span></td>
                <td><a href="/scores/trend/${p.studentId}">${p.studentName}</a></td>
                <td><small class="text-muted">${p.studentNo}</small></td>
                <td>${fmt1(p.prevTotal)}</td>
                <td><b>${fmt1(p.curTotal)}</b></td>
                <td><span class="badge bg-success">+${fmt1(p.delta)}</span></td>
                <td>${p.prevRank}</td>
                <td><b>${p.curRank}</b></td>
                <td><span class="badge bg-success">↑${p.rankDelta}名</span></td>
              </tr>`).join('')
            : '<tr><td colspan="9" class="text-center text-muted py-3">无数据</td></tr>';
        }
        // 渲染退步榜
        if (regressTbody) {
          regressTbody.innerHTML = data.regress.length
            ? data.regress.map((p, i) => `
              <tr>
                <td><span class="badge bg-danger">${i+1}</span></td>
                <td><a href="/scores/trend/${p.studentId}">${p.studentName}</a></td>
                <td><small class="text-muted">${p.studentNo}</small></td>
                <td>${fmt1(p.prevTotal)}</td>
                <td><b>${fmt1(p.curTotal)}</b></td>
                <td><span class="badge bg-danger">${fmt1(p.delta)}</span></td>
                <td>${p.prevRank}</td>
                <td><b>${p.curRank}</b></td>
                <td><span class="badge bg-danger">↓${-p.rankDelta}名</span></td>
              </tr>`).join('')
            : '<tr><td colspan="9" class="text-center text-muted py-3">无数据</td></tr>';
        }
        // 渲染全员升降榜 (按 rankDelta 降序: 进步在前, 退步在后)
        if (allTbody) {
          const allSorted = (data.all || []).slice().sort((a, b) => b.rankDelta - a.rankDelta);
          allTbody.innerHTML = allSorted.length
            ? allSorted.map((p, i) => {
                const rd = p.rankDelta;
                const badge = rd > 0 ? `<span class="badge bg-success">↑${rd}</span>`
                              : rd < 0 ? `<span class="badge bg-danger">↓${-rd}</span>`
                              : `<span class="badge bg-secondary">持平</span>`;
                const deltaCls = p.delta > 0 ? 'text-success' : (p.delta < 0 ? 'text-danger' : '');
                const deltaSign = p.delta > 0 ? '+' : '';
                return `
              <tr>
                <td>${i+1}</td>
                <td><a href="/scores/trend/${p.studentId}">${p.studentName}</a></td>
                <td><small class="text-muted">${p.studentNo}</small></td>
                <td>${fmt1(p.prevTotal)}</td>
                <td><b>${fmt1(p.curTotal)}</b></td>
                <td class="${deltaCls} fw-bold">${deltaSign}${fmt1(p.delta)}</td>
                <td>${p.prevRank ?? '-'}</td>
                <td><b>${p.curRank ?? '-'}</b></td>
                <td>${badge}</td>
              </tr>`;
              }).join('')
            : '<tr><td colspan="9" class="text-center text-muted py-3">无数据</td></tr>';
        }
        if (meta) {
          if (data.prevName) {
            meta.innerHTML = `<i class="bi bi-info-circle"></i> 本次: <b>${data.examName}</b> · 上次: <b>${data.prevName}</b> · 共对比 ${data.total} 人`;
          } else {
            meta.innerHTML = `<i class="bi bi-info-circle"></i> ${data.examName} 之前没有考试,无法生成对比榜`;
          }
        }
      })
      .catch(err => {
        if (meta) meta.innerHTML = `<i class="bi bi-exclamation-triangle"></i> 加载失败: ${err.message}`;
      });
  };

  // 日常: 类型分布饼图
  window.initDailyPie = function () {
    const el = document.getElementById('daily-pie');
    if (!el || typeof echarts === 'undefined') return;
    const chart = echarts.init(el);
    chart.showLoading('default', { text: '加载中...', color: '#e15759' });
    fetchJSON('/daily/api/stats')
      .then(data => {
        chart.hideLoading();
        chart.setOption({
          tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
          legend: { top: 0, type: 'scroll' },
          series: [{
            type: 'pie',
            radius: ['40%', '70%'],
            center: ['50%', '55%'],
            data: data.pie.filter(d => d.value > 0),
            label: { formatter: '{b}\n{c} 条' }
          }]
        });
      })
      .catch(err => {
        chart.hideLoading();
        chart.setOption({ title: { text: '加载失败',
                                   left: 'center', top: 'center',
                                   textStyle: { color: '#dc3545', fontSize: 14 } } });
      });
    window.addEventListener('resize', () => chart.resize());
  };

  // 日常: 违纪 Top10 横向条形图
  window.initDailyPunish = function () {
    const el = document.getElementById('daily-punish');
    if (!el || typeof echarts === 'undefined') return;
    const chart = echarts.init(el);
    fetchJSON('/daily/api/stats')
      .then(data => {
        const items = data.punishTop.slice().reverse();
        chart.setOption({
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
          grid: { left: 80, right: 30, top: 10, bottom: 30 },
          xAxis: { type: 'value', minInterval: 1 },
          yAxis: { type: 'category',
                    data: items.map(i => i.name) },
          series: [{
            type: 'bar', data: items.map(i => i.count),
            itemStyle: { color: '#e15759' },
            label: { show: true, position: 'right' }
          }]
        });
        // 点击跳转
        chart.on('click', params => {
          const item = items[params.dataIndex];
          if (item && item.studentId) {
            window.location.href = `/daily/student/${item.studentId}`;
          }
        });
      })
      .catch(err => chart.setOption({ title: { text: '加载失败',
        left: 'center', top: 'center',
        textStyle: { color: '#dc3545', fontSize: 14 } } }));
    window.addEventListener('resize', () => chart.resize());
  };

  // 日常: 表扬 Top10 横向条形图
  window.initDailyPraise = function () {
    const el = document.getElementById('daily-praise');
    if (!el || typeof echarts === 'undefined') return;
    const chart = echarts.init(el);
    fetchJSON('/daily/api/stats')
      .then(data => {
        const items = data.praiseTop.slice().reverse();
        chart.setOption({
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
          grid: { left: 80, right: 30, top: 10, bottom: 30 },
          xAxis: { type: 'value', minInterval: 1 },
          yAxis: { type: 'category',
                    data: items.map(i => i.name) },
          series: [{
            type: 'bar', data: items.map(i => i.count),
            itemStyle: { color: '#59a14f' },
            label: { show: true, position: 'right' }
          }]
        });
        chart.on('click', params => {
          const item = items[params.dataIndex];
          if (item && item.studentId) {
            window.location.href = `/daily/student/${item.studentId}`;
          }
        });
      })
      .catch(err => chart.setOption({ title: { text: '加载失败',
        left: 'center', top: 'center',
        textStyle: { color: '#dc3545', fontSize: 14 } } }));
    window.addEventListener('resize', () => chart.resize());
  };

  // 偏科诊断: 得分率 vs 均分得分率 柱状图
  window.initDiagnosis = function (diagData) {
    const el = document.getElementById('diagnosis-chart');
    if (!el || typeof echarts === 'undefined' || !diagData || !diagData.length) return;
    const chart = echarts.init(el);
    chart.setOption({
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: function (params) {
          let s = params[0].name + '<br/>';
          params.forEach(p => {
            s += `${p.marker} ${p.seriesName}: ${Number(p.value).toFixed(1)}%<br/>`;
          });
          return s;
        }
      },
      legend: { top: 0 },
      grid: { left: 50, right: 30, top: 40, bottom: 30 },
      xAxis: { type: 'category', data: diagData.map(d => d.label) },
      yAxis: { type: 'value', max: 100, name: '得分率%' },
      series: [
        {
          name: '个人得分率',
          type: 'bar',
          data: diagData.map(d => Number(d.rate).toFixed(1)),
          itemStyle: {
            color: function (p) {
              const d = diagData[p.dataIndex];
              if (d.status === 'weak') return '#e15759';
              if (d.status === 'strong') return '#59a14f';
              return '#4e79a7';
            }
          },
          label: { show: true, position: 'top', formatter: '{c}%' }
        },
        {
          name: '班级均分得分率',
          type: 'bar',
          data: diagData.map(d => Number(d.avg_rate).toFixed(1)),
          itemStyle: { color: '#aaa' },
          label: { show: true, position: 'top', formatter: '{c}%' }
        }
      ]
    });
    window.addEventListener('resize', () => chart.resize());
  };

  // 班级历次考试趋势
  window.initClassTrend = function () {
    const totalEl = document.getElementById('class-trend-total');
    const subjEl = document.getElementById('class-trend-subjects');
    if (typeof echarts === 'undefined') return;

    fetchJSON('/scores/api/class-trend')
      .then(data => {
        if (!data.exams || !data.exams.length) return;
        // 主图: 总分均分/最高/最低
        if (totalEl) {
          const c1 = echarts.init(totalEl);
          const totalAvg = data.series.find(s => s.name === '总分均分') || { data: [] };
          const totalMax = data.series.find(s => s.name === '总分最高') || { data: [] };
          const totalMin = data.series.find(s => s.name === '总分最低') || { data: [] };
          c1.setOption({
            tooltip: { trigger: 'axis',
              valueFormatter: v => v != null ? Number(v).toFixed(1) : '-' },
            legend: { data: ['总分均分', '总分最高', '总分最低'], top: 0 },
            grid: { left: 50, right: 30, top: 40, bottom: 60 },
            xAxis: { type: 'category', data: data.exams,
                     axisLabel: { rotate: 20 } },
            yAxis: { type: 'value', name: '分数' },
            series: [
              { name: '总分均分', type: 'line', data: totalAvg.data, smooth: true,
                itemStyle: { color: COLORS.bar },
                label: { show: true, formatter: p => p.value != null ? Number(p.value).toFixed(1) : '' } },
              { name: '总分最高', type: 'line', data: totalMax.data, smooth: true,
                itemStyle: { color: COLORS.max }, symbol: 'circle', symbolSize: 6 },
              { name: '总分最低', type: 'line', data: totalMin.data, smooth: true,
                itemStyle: { color: COLORS.min }, symbol: 'rect', symbolSize: 6 }
            ]
          });
          window.addEventListener('resize', () => c1.resize());
        }
        // 副图: 各科均分趋势
        if (subjEl) {
          const c2 = echarts.init(subjEl);
          const subjectSeries = data.series.filter(s =>
            s.name !== '总分均分' && s.name !== '总分最高' && s.name !== '总分最低');
          c2.setOption({
            tooltip: { trigger: 'axis',
              valueFormatter: v => v != null ? Number(v).toFixed(1) : '-' },
            legend: { type: 'scroll', top: 0,
                      data: subjectSeries.map(s => s.name) },
            grid: { left: 40, right: 20, top: 40, bottom: 60 },
            xAxis: { type: 'category', data: data.exams,
                     axisLabel: { rotate: 20 } },
            yAxis: { type: 'value', name: '均分' },
            series: subjectSeries.map(s => ({
              name: s.name, type: 'line', data: s.data, smooth: true,
              connectNulls: true, lineStyle: { width: 1.5 }
            }))
          });
          window.addEventListener('resize', () => c2.resize());
        }
      })
      .catch(err => {
        if (totalEl) {
          const c = echarts.init(totalEl);
          c.setOption({ title: { text: '加载失败: ' + err.message,
                                  left: 'center', top: 'center',
                                  textStyle: { color: '#dc3545', fontSize: 14 } } });
        }
      });
  };

  // 目标对比雷达图
  window.initGoalCompare = function (studentId, term, targets) {
    const el = document.getElementById('goal-radar');
    if (!el || typeof echarts === 'undefined') return;
    const chart = echarts.init(el);
    chart.showLoading('default', { text: '加载中...', color: COLORS.personal });
    const subjects = ['chinese', 'math', 'english', 'physics', 'chemistry',
                       'biology', 'politics', 'history', 'geography'];
    const labels = { chinese:'语文', math:'数学', english:'英语', physics:'物理',
                     chemistry:'化学', biology:'生物', politics:'政治',
                     history:'历史', geography:'地理' };
    const fulls = { chinese:150, math:150, english:150, physics:100,
                    chemistry:100, biology:100, politics:100,
                    history:100, geography:100 };
    const indicators = subjects.map(s => ({ name: labels[s], max: fulls[s] }));
    const targetVals = subjects.map(s => (targets && targets[s]) ? Number(targets[s]) : 0);
    const actualVals = [];

    fetchJSON(`/scores/api/trend/${studentId}`)
      .then(data => {
        const examCount = data.exams ? data.exams.length : 0;
        const lastIdx = examCount - 1;
        subjects.forEach(subj => {
          const series = data.series.find(s => s.name === labels[subj]);
          const actual = series && lastIdx >= 0 ? series.data[lastIdx] : null;
          actualVals.push(actual || 0);
        });
        chart.hideLoading();
        chart.setOption({
          tooltip: { trigger: 'item',
            valueFormatter: v => v != null ? Number(v).toFixed(1) : '-' },
          legend: { data: ['目标', '实际'], top: 0 },
          radar: {
            indicator: indicators,
            shape: 'polygon', splitNumber: 5,
            axisName: { color: '#666', fontSize: 11 }
          },
          series: [{
            type: 'radar',
            data: [
              { name: '目标', value: targetVals,
                itemStyle: { color: COLORS.max },
                areaStyle: { color: 'rgba(225,87,89,0.15)' } },
              { name: '实际', value: actualVals,
                itemStyle: { color: COLORS.avg },
                areaStyle: { color: 'rgba(89,161,79,0.2)' } }
            ]
          }]
        });
        window.addEventListener('resize', () => chart.resize());
      })
      .catch(err => {
        chart.hideLoading();
        chart.setOption({ title: { text: '加载失败: ' + err.message,
                                   left: 'center', top: 'center',
                                   textStyle: { color: '#dc3545', fontSize: 14 } } });
      });
  };

  // 学科均衡度: 箱线图 + CV对比
  window.initBalance = function (examId, cvData) {
    const boxEl = document.getElementById('balance-box');
    const cvEl = document.getElementById('balance-cv');
    if (typeof echarts === 'undefined') return;

    // 箱线图
    if (boxEl) {
      const chart = echarts.init(boxEl);
      chart.showLoading('default', { text: '加载中...', color: COLORS.bar });
      fetchJSON(`/scores/api/balance/${examId}`)
        .then(data => {
          chart.hideLoading();
          // ECharts boxplot: [min, Q1, median, Q3, max]
          const boxData = data.boxes.map(b => [b.min, b.q1, b.median, b.q3, b.max]);
          const cats = data.boxes.map(b => b.name);
          chart.setOption({
            tooltip: { trigger: 'item' },
            grid: { left: 50, right: 30, top: 30, bottom: 60 },
            xAxis: { type: 'category', data: cats,
                     axisLabel: { rotate: 30 } },
            yAxis: { type: 'value', name: '分数' },
            series: [{
              name: '分数分布',
              type: 'boxplot',
              data: boxData,
              itemStyle: { color: '#b3cde3', borderColor: '#4e79a7' }
            }]
          });
          window.addEventListener('resize', () => chart.resize());
        })
        .catch(err => {
          chart.hideLoading();
          chart.setOption({ title: { text: '加载失败: ' + err.message,
                                     left: 'center', top: 'center',
                                     textStyle: { color: '#dc3545', fontSize: 14 } } });
        });
    }
    // CV对比图
    if (cvEl) {
      const c2 = echarts.init(cvEl);
      const cats = cvData.map(d => d.label);
      const cvVals = cvData.map(d => Number(d.cv));
      c2.setOption({
        tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },
          formatter: function (params) {
            const d = cvData[params[0].dataIndex];
            return `${d.label}<br/>CV: ${d.cv}%<br/>均分: ${Number(d.avg).toFixed(1)}<br/>标准差: ${Number(d.std).toFixed(1)}`;
          }
        },
        grid: { left: 50, right: 30, top: 30, bottom: 60 },
        xAxis: { type: 'category', data: cats, axisLabel: { rotate: 30 } },
        yAxis: { type: 'value', name: 'CV%' },
        series: [{
          name: '变异系数',
          type: 'bar',
          data: cvVals.map((v, i) => ({
            value: v,
            itemStyle: { color: v < 15 ? '#59a14f' : (v < 25 ? '#f28e2b' : '#e15759') }
          })),
          barMaxWidth: 40,
          label: { show: true, position: 'top', formatter: '{c}%' }
        }]
      });
      window.addEventListener('resize', () => c2.resize());
    }
  };
})();
