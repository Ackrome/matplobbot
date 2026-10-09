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
