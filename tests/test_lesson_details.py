"""Exercise the browser model in Node without browser/API dependencies."""

import os
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "node is required for lesson-details tests")
class LessonDetailsTests(unittest.TestCase):
    def run_model(self, assertions):
        script = (
            """
            const assert = require('node:assert/strict');
            const fs = require('node:fs'), vm = require('node:vm');
            const sandbox = {window: {}, URL};
            vm.createContext(sandbox);
            vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), sandbox);
            const {normalizeLesson: normalize, relatedLessons: related} = sandbox.window.MpbLessonDetails;
            const entity = {type:'group', id:'7', name:'ПМ23-1'};
            const base = {date:'2026.10.09', beginLesson:'02:15', endLesson:'03:45',
                discipline:'Short', discipline_full:'Полное название', discipline_short:'ПН',
                module:'Module', lecturer:'123', lecturer_title:'Иванов_Иван_Иванович',
                auditorium:'B4/10', group:'ПМ23-1'};
        """
            + assertions
        )
        result = subprocess.run(
            ["node", "-e", script, str(ROOT / "main_site_frontend/js/lesson_details.js")],
            cwd=ROOT,
            env={**os.environ, "TZ": "America/Los_Angeles"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_full_names_optional_metadata_and_identifiers(self):
        self.run_model("""
            const item = normalize({...base, lecturerEmail:'a@example.edu; a@example.edu, b@example.edu',
                building:'Main campus', subgroup:'2', notes:'Bring a laptop'}, entity);
            assert.equal(item.title, 'Полное название');
            assert.equal(item.teacher, 'Иванов Иван Иванович');
            assert.equal(item.teacherId, '123');
            assert.equal(item.emails.join(','), 'a@example.edu,b@example.edu');
            assert.equal(item.groupId, '7');
            assert.equal(normalize({...base, group:'ПМ23-2'}, entity).groupId, '');
            assert.equal(item.subgroup, '2');
            assert.equal(item.building, 'Main campus');
            assert.equal(normalize({lecturer:'123'}).teacher, '');
            assert.equal(normalize({lecturer:'abc-123-def'}).teacher, '');
            assert.equal(normalize({lecturer:'Иванов И.И.'}).teacher, 'Иванов И.И.');
            assert.equal(normalize({...base, building:'B4'}).building, '');
        """)

    def test_moscow_dates_and_invalid_intervals(self):
        self.run_model("""
            const item = normalize(base);
            assert.equal(item.date, '2026-10-09');
            assert.equal(new Date(item.startAt).toISOString(), '2026-10-08T23:15:00.000Z');
            assert.equal(item.duration, 90);
            assert.equal(normalize({...base, date:'2026-02-30'}).duration, null);
            assert.equal(normalize({...base, beginLesson:'24:00'}).startAt, null);
            assert.equal(normalize({...base, endLesson:'01:00'}).duration, null);
            assert.equal(normalize({...base, endLesson:'02:15'}).duration, null);
            assert.equal(normalize({}).duration, null);
        """)

    def test_untrusted_urls_are_filtered(self):
        self.run_model("""
            const item = normalize({...base, url:'javascript:alert(1)', url1:'https://example.edu/course',
                url2:'https://example.edu/course', onlineUrl:'data:text/html,attack',
                streamUrl:'https://user:secret@example.edu/' });
            assert.equal(item.links.join(','), 'https://example.edu/course');
            assert.equal(normalize({url:'http://example.edu/'}).links.length, 1);
            assert.equal(normalize({url:{bad:'value'}}).links.length, 0);
        """)

    def test_related_classes_remove_duplicates_but_preserve_parallel_groups(self):
        self.run_model("""
            const future = {...base, date:'2026.10.16'};
            const selected = normalize(base, entity);
            const rows = [future, {...base}, {...base, lessonOid:999},
                {...base, auditorium:'B4/11'}, {...base, subgroup:'2'},
                {...base, lecturer_title:'Другой преподаватель'},
                {...base, group:'ПМ23-2'}, {...base, discipline_full:'Other'},
                {...base, module:'Different module'}];
            const result = related(selected, rows, entity);
            assert.equal(result.length, 6);
            assert.equal(result.at(-1).date, '2026-10-16');
            assert.equal(result.filter(item=>item.raw===base).length, 1);
            assert.equal(result.filter(item=>item.subgroup==='2').length, 1);
            assert.equal(result.filter(item=>item.group==='ПМ23-2').length, 1);
            assert.equal(related(normalize({}), [{}]).length, 1);
        """)

    def test_complete_cache_replaces_window_and_does_not_restore_removed_classes(self):
        self.run_model("""
            const selected = normalize(base, entity);
            const semester = [{...base, date:'2027.01.31'}, {...base, date:'2026.08.25'},
                {...base, date:'2026.08.25', subgroup:'2'}, {...base, date:'2026.08.25'},
                {...base, discipline_full:'Other'}];
            const result = related(selected, semester, entity, false);
            assert.equal(result.length, 3);
            assert.equal(result[0].date, '2026-08-25');
            assert.equal(result.at(-1).date, '2027-01-31');
            assert.equal(result.some(item=>item.date==='2026-10-09'), false);
            assert.equal(related(selected, [], entity, false).length, 0);
            assert.equal(related(selected, [], entity).length, 1);
        """)

    def test_explicit_discipline_ids_take_precedence_over_titles(self):
        self.run_model("""
            const chosen = {...base, disciplineOid:1};
            const result = related(normalize(chosen), [
                {...chosen, discipline_full:'Alternate spelling', date:'2026.10.10'},
                {...chosen, disciplineOid:2},
                {...base, discipline_full:'  Полное   название ', date:'2026.10.11'},
            ]);
            assert.equal(result.length, 3);
            assert.equal(result.some(item=>item.disciplineId==='2'), false);
        """)

    def test_curriculum_context_uses_student_group_and_selected_lesson_date(self):
        self.run_model("""
            const context = sandbox.window.MpbLessonDetails.curriculumContext;
            const selected = normalize({...base, groupOid:88}, entity);
            const request = context(selected, entity);
            assert.equal(request.group_id, '7');
            assert.equal(request.discipline, 'Полное название');
            assert.equal(request.lesson_date, '2026-10-09');
            const teacher = {type:'person', id:'999', name:'Teacher'};
            assert.equal(context(normalize(base, teacher), teacher), null);
            assert.equal(context(normalize({...base, groupOid:88}, teacher), teacher).group_id, '88');
            assert.equal(context(normalize({...base, groupOid:'88,99'}, teacher), teacher), null);
            assert.equal(context(normalize({...base, date:'not-a-date'}, entity), entity), null);
            assert.equal(context(normalize({...base, discipline:'', discipline_full:'', discipline_short:''}, entity), entity), null);
            const other = context(normalize({...base, group:'ПМ23-2', groupOid:8, date:'2027.03.05'}, entity), entity);
            assert.equal(other.group_id, '7');
            assert.equal(other.lesson_date, '2027-03-05');
        """)

    def test_group_timetable_curriculum_uses_parent_for_module_and_shared_classes(self):
        self.run_model("""
            const {curriculumContext: context, curriculumGroup: group} = sandbox.window.MpbLessonDetails;
            const main = {type:'group', id:'162426', name:'ПМ23-1'};
            for (const label of ['003860_4 Модуль "Машинное обучение на графах" - 1',
                '003860_4 Модуль "Разработка распределенных при - 1',
                '006088_2 Иностранный язык (КАЯиПК)-1', 'ПМ23-2']) {
                const selected = normalize({...base, group:label, groupOid:162215,
                    discipline_full:'Машинное обучение на графах'}, main);
                assert.equal(context(selected, main).group_id, '162426');
                assert.equal(context(selected, main).discipline, 'Машинное обучение на графах');
                assert.equal(group(selected, main).name, 'ПМ23-1');
                // Preserve the actual lesson group for occurrence/action navigation.
                assert.equal(selected.groupId, '162215');
                assert.equal(selected.group, label);
            }
            const selected = normalize({...base, group:'Module', groupOid:162215}, main);
            assert.equal(group(selected, {...main, name:''}).name, '162426');
            for (const id of ['', '0', '162426,162428', 'unknown']) {
                assert.equal(context(selected, {...main, id}), null);
                assert.equal(group(selected, {...main, id}), null);
            }
        """)

    def test_teacher_and_room_curriculum_keep_lesson_group_and_label(self):
        self.run_model("""
            const {curriculumContext: context, curriculumGroup: group} = sandbox.window.MpbLessonDetails;
            for (const type of ['person', 'auditorium']) {
                const entity = {type, id:'999', name:'Not a student group'};
                const raw = {...base, group:'003860_4 Модуль "Машинное обучение на графах" - 1', groupOid:162215};
                const selected = normalize(raw, entity);
                assert.equal(context(selected, entity).group_id, '162215');
                assert.equal(group(selected, entity).name, raw.group);
                for (const groupOid of [undefined, '0', '162426,162428']) {
                    assert.equal(context(normalize({...raw, groupOid}, entity), entity), null);
                }
                assert.equal(group(normalize({...raw, group:''}, entity), entity).name, '162215');
            }
        """)

    def test_curriculum_assessments_preserve_terms_and_reject_untrusted_provenance(self):
        self.run_model("""
            const normalizeCurriculum = sandbox.window.MpbLessonDetails.normalizeCurriculum;
            const assessment = {kind:'exam', semester:7, source_url:'https://www.fa.ru/upload/plan.pdf',
                source_title:'Official plan', page:12};
            const response = {status:'confirmed', group_id:7, semester:7, admission_year:2023,
                program:'Applied mathematics', assessments:[assessment,
                    {...assessment, kind:'coursework'}, {...assessment, kind:'graded_pass', semester:8}],
                checked_at:'2026-10-09T09:00:00Z', stale:true};
            const result = normalizeCurriculum(response, '7');
            assert.equal(result.assessments.length, 3);
            assert.equal(result.assessments[2].kind, 'graded_pass');
            assert.equal(result.assessments[2].semester, 8);
            assert.equal(result.assessments[0].sourceUrl, 'https://www.fa.ru/upload/plan.pdf#page=12');
            assert.equal(result.admissionYear, '2023');
            assert.equal(result.stale, true);
            for (const url of ['javascript:alert(1)', 'https://fa.ru.attacker.example/plan.pdf',
                'https://user:password@www.fa.ru/plan.pdf', 'http://www.fa.ru/plan.pdf']) {
                assert.equal(normalizeCurriculum({...response, assessments:[{...assessment, source_url:url}]}, '7'), null);
            }
            assert.equal(normalizeCurriculum(response, '8'), null);
            assert.equal(normalizeCurriculum({...response, assessments:[]}, '7'), null);
            assert.equal(normalizeCurriculum({...response, semester:null}, '7'), null);
            assert.equal(normalizeCurriculum({...response, assessments:[{...assessment, kind:'test'}]}, '7'), null);
            assert.equal(normalizeCurriculum({...response, assessments:[{...assessment, semester:0}]}, '7'), null);
            const unavailable = normalizeCurriculum({status:'unmapped', group_id:'7', assessments:[]}, '7');
            assert.equal(unavailable.status, 'unmapped');
            assert.equal(unavailable.assessments.length, 0);
        """)

    def test_curriculum_snapshot_resolves_only_immutable_paths_at_configured_api(self):
        self.run_model("""
            const normalizeCurriculum = sandbox.window.MpbLessonDetails.normalizeCurriculum;
            sandbox.window.location = {origin:'https://site.example'};
            sandbox.window.getMpbApiBase = () => 'https://api.example/custom-api';
            const snapshot = '/api/schedule/curriculum/documents/42/' + 'a'.repeat(64) + '.pdf';
            const assessment = {kind:'pass', semester:7, source_url:'https://www.fa.ru/upload/plan.pdf',
                snapshot_url:snapshot, page:3};
            const response = {status:'confirmed', group_id:7, semester:7, assessments:[assessment]};
            const read = item => normalizeCurriculum({...response, assessments:[item]}, '7').assessments[0];
            assert.equal(read(assessment).snapshotUrl, 'https://api.example/custom-api/schedule/curriculum/documents/42/' + 'a'.repeat(64) + '.pdf#page=3');
            for (const invalid of ['https://attacker.example/file.pdf', '//attacker.example/file.pdf',
                snapshot + '?redirect=https://attacker.example', '/api/../../secret', '/api/schedule/curriculum/documents/42/latest.pdf']) {
                assert.equal(read({...assessment, snapshot_url:invalid}).snapshotUrl, '');
            }
            sandbox.window.getMpbApiBase = () => '/api';
            assert.equal(read(assessment).snapshotUrl, 'https://site.example' + snapshot + '#page=3');
        """)

    def test_card_actions_preserve_each_source_object_and_known_entity_id(self):
        self.run_model("""
            const source = fs.readFileSync('main_site_frontend/js/schedule.js', 'utf8');
            const actionFunction = source.slice(source.indexOf('function getLessonActionId('),
                source.indexOf('function getLessonActionLabels('));
            const navigateFunction = source.slice(source.indexOf('async function openLessonEntitySchedule('),
                source.indexOf('window.runLessonAction ='));
            const actions = {lessonActionMap:new Map(), lessonActionIds:new WeakMap(), nextLessonActionId:0,
                window:{ScheduleApi:{searchEntities:async()=>[{id:'999',label:'Wrong teacher'}]}},
                loadSchedule:async(...args)=>{actions.destination=args;}, console};
            vm.createContext(actions); vm.runInContext(actionFunction + navigateFunction, actions);
            const first = {...base, subgroup:'1'}, second = {...base, subgroup:'2'};
            const firstId = actions.getLessonActionId(first), secondId = actions.getLessonActionId(second);
            assert.notEqual(firstId, secondId);
            assert.equal(actions.lessonActionMap.get(firstId), first);
            assert.equal(actions.lessonActionMap.get(secondId), second);
            assert.equal(actions.getLessonActionId(first), firstId);
            actions.lessonActionMap.clear(); actions.getLessonActionId(first);
            assert.equal(actions.lessonActionMap.get(firstId), first);
            actions.openLessonEntitySchedule('person', '123', 'Иванов').then(()=>{
                assert.equal(actions.destination[1], '123');
            });
        """)


if __name__ == "__main__":
    unittest.main()
