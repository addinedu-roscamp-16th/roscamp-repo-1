# FryBot API: the only door between ROS (laptop) and MySQL. ROS never touches the DB directly.
import json
import os
from contextlib import contextmanager

import pymysql
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title='FryBot API')
# intent_matcher menu key -> menu.name in DB (SR-009 seed: 치킨, 볶음밥)
MENU_KEY_TO_NAME = {'chicken': '치킨', 'fried_rice': '볶음밥'}


@contextmanager
def db():
    conn = pymysql.connect(host=os.environ.get('DB_HOST', 'db'), user=os.environ['DB_USER'],
                           password=os.environ['DB_PASSWORD'], database=os.environ.get('DB_NAME', 'frybot'),
                           charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class VoiceCommand(BaseModel):
    table_id: int
    intent: str
    menu: list[str] = []
    qty: int | None = None
    text: str = ''
    normalized: str = ''


@app.get('/health')
def health():
    with db() as c, c.cursor() as cur:
        cur.execute('SELECT MAX(version) AS v FROM schema_version')
        return {'ok': True, 'schema_version': cur.fetchone()['v']}


@app.get('/tables')
def tables():
    with db() as c, c.cursor() as cur:
        cur.execute('SELECT * FROM v_table_board ORDER BY table_id')
        return cur.fetchall()


@app.get('/orders/{order_id}')
def order(order_id: int):
    with db() as c, c.cursor() as cur:
        cur.execute('SELECT * FROM v_order_progress WHERE order_id=%s', (order_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, 'order not found')
        cur.execute('SELECT m.name, oi.qty FROM order_item oi JOIN menu m USING (menu_id) WHERE order_id=%s',
                    (order_id,))
        row['items'] = cur.fetchall()
        return row


def log(cur, entity, entity_id, to_state, message, detail):
    cur.execute('INSERT INTO event_log (entity, entity_id, to_state, actor, message, detail) '
                'VALUES (%s,%s,%s,%s,%s,%s)',
                (entity, str(entity_id), to_state, 'TABLE_UI', message[:500], json.dumps(detail, ensure_ascii=False)))


@app.post('/voice/command')
def voice_command(cmd: VoiceCommand):
    """Voice result from ROS. 'order' creates an order; other intents are logged for the workflow."""
    with db() as c, c.cursor() as cur:
        if cmd.intent != 'order':
            log(cur, 'TABLE', cmd.table_id, None, f'voice:{cmd.intent} "{cmd.text}"', cmd.model_dump())
            return {'accepted': True, 'intent': cmd.intent, 'order_id': None}

        names = [MENU_KEY_TO_NAME[k] for k in cmd.menu if k in MENU_KEY_TO_NAME]
        if not names:
            raise HTTPException(422, f'menu not on sale: {cmd.menu}')
        # SR-004: order belongs to the group currently seated at that table
        cur.execute("SELECT visit_id FROM visit WHERE active_table_id=%s AND status='IN_USE'", (cmd.table_id,))
        visit = cur.fetchone()
        if not visit:
            raise HTTPException(409, f'no seated customer (IN_USE visit) at table {cmd.table_id}')
        cur.execute('INSERT INTO orders (visit_id, table_id) VALUES (%s,%s)', (visit['visit_id'], cmd.table_id))
        order_id = cur.lastrowid
        for name in names:
            cur.execute('INSERT INTO order_item (order_id, menu_id, qty) SELECT %s, menu_id, %s FROM menu WHERE name=%s',
                        (order_id, cmd.qty or 1, name))
        log(cur, 'ORDER', order_id, 'ORDERED', f'voice order "{cmd.text}"', cmd.model_dump())
        return {'accepted': True, 'intent': 'order', 'order_id': order_id, 'items': names, 'qty': cmd.qty or 1}
