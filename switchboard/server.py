# -*- coding: utf-8 -*-
# pylint: disable=C0411, C0412, C0413
'''a Flask application making up the Switchboard http server'''

from gevent import monkey
monkey.patch_all()
from flask import Flask, Blueprint, request, Response, abort, render_template
from flask_restplus import Api, Resource
from flask_socketio import SocketIO, Namespace, emit, join_room, rooms
from flask_bootstrap import Bootstrap
from gevent.pywsgi import WSGIServer, LoggingLogAdapter
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from prometheus_client.core import REGISTRY
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import json
import logging
from switchboard.version import __version__, get_build_info
from switchboard.argparser import get_pars
from switchboard.sensors import Sensors

# create logger
logger = logging.getLogger(__name__)

# get parameters from command line arguments
pars = get_pars()

# set logger
logging.basicConfig(format='%(levelname)s %(module)s: %(message)s',
                    level=pars.log_level)
logging.getLogger('apscheduler').setLevel(logging.WARNING)


# Socket.IO namespaces
class SensorsNamespace(Namespace):
    def on_sensor_response(self, message):
        logger.debug('SocketIO: {} '.format(message))
        for node_id in message:
            request_form = message[node_id]
            logger.info('SocketIO in: {}: {}'.format(node_id,
                                                     str(request_form)))
            try:
                sensors.set_values(node_id, request_form)
            except KeyError:
                pass

    def on_join(self, message):
        logger.debug('SocketIO client join: {} '.format(message))
        gw = message['room']
        join_room(gw)
        emit('status_response', {'joined in': rooms()})
        emit('config_response', {gw: list(sensors.get_config_of_gw(gw))})

    def on_connect(self):
        emit('status_response', {'status': 'connected'})

    def on_ping(self):
        emit('pong')


class EventsNamespace(Namespace):
    def on_connect(self):
        emit('event',
             json.dumps(sensors.get_metrics_dict_by_node(skip_None=False)),
             broadcast=True)

    def on_ping(self):
        emit('pong')


# create Flask application
app = Flask(__name__)
blueprint = Blueprint('api', __name__, url_prefix='/api')
api = Api(blueprint, doc='/', title='Switchboard API', version=__version__)
bootstrap = Bootstrap(app)
sensors = Sensors()
app.config.SWAGGER_UI_DOC_EXPANSION = 'list'
app.register_blueprint(blueprint)
REGISTRY.register(sensors.CustomCollector(sensors))

sio = SocketIO(app, async_mode='gevent')
sio.on_namespace(SensorsNamespace('/sensors'))
sio.on_namespace(EventsNamespace('/events'))
sensors.sio = sio

# REST API methods

ns_metrics = api.namespace('metrics',
                           description='methods for manipulating metrics',
                           path='/metrics')
ns_state = api.namespace('state',
                         description='methods for manipulating process state',
                         path='/state')
ns_info = api.namespace('info',
                        description='methods to obtain information',
                        path='/info')

parser = api.parser()
for sensor_id, t, t_str in sensors.get_parser_arguments():
    parser.add_argument(sensor_id,
                        type=t,
                        required=False,
                        help='{} value for sensor {}'.format(t_str, sensor_id),
                        location='form')


@ns_metrics.route('/<string:node_id>')
class NodeMetrics(Resource):
    @api.doc(params={'node_id': 'a node to be affected'})
    @api.response(200, 'Success')
    @api.response(404, 'Node or sensor not found')
    @api.expect(parser)
    def put(self, node_id):
        '''set sensors of a node'''
        logger.info("API/set: {}: {}".format(node_id,
                                             str(request.form.to_dict())))
        try:
            ret = sensors.set_values(node_id, request.form)
        except KeyError:
            logger.warning("node {} or sensor not found".format(node_id))
            abort(404)  # sensor not configured

        return ret

    @api.doc(params={'node_id': 'a node from which to get metrics'})
    @api.response(200, 'Success')
    @api.response(404, 'Node not found')
    def get(self, node_id):
        '''get sensor metrics of a node'''

        try:
            ret = dict(sensors.get_metrics_of_node(node_id))
        except KeyError:
            logger.warning("node {} not found".format(node_id))
            abort(404)  # sensor not configured

        return ret


@ns_metrics.route('/inc/<string:node_id>')
class IncNodeMetrics(Resource):
    @api.doc(params={'node_id': 'a node to be affected'})
    @api.response(200, 'Success')
    @api.response(404, 'Node or sensor not found')
    @api.expect(parser)
    def put(self, node_id):
        '''increment sensor values of a node'''
        logger.info("API/inc: {}: {}".format(node_id,
                                             str(request.form.to_dict())))
        try:
            ret = sensors.set_values(node_id, request.form, increment=True)
        except KeyError:
            logger.warning("node {} or sensor not found".format(node_id))
            abort(404)  # sensor not configured

        return ret


@ns_metrics.route('/<string:node_id>/<string:sensor_id>')
class SensorMetrics(Resource):
    @api.doc(
        params={
            'node_id': 'a node where a sensor belongs',
            'sensor_id': 'a sensor from which to get metrics'
        })
    @api.response(200, 'Success')
    @api.response(404, 'Node or sensor not found')
    def get(self, node_id, sensor_id):
        '''get metrics of one sensor'''

        try:
            ret = dict(sensors.get_metrics_of_sensor(node_id, sensor_id))
        except KeyError:
            logger.warning("node {} or sensor {} not found".format(
                node_id, sensor_id))
            abort(404)  # sensor not configured

        return ret


@ns_metrics.route('/')
class SensorsMetricsList(Resource):
    def get(self):
        '''get a list of all metrics'''

        return list(sensors.get_metrics(skip_None=False))


@ns_metrics.route('/by_gw')
class SensorsMetricsByGw(Resource):
    def get(self):
        '''get all metrics sorted by gateway / node_id / sensor_id'''

        return sensors.get_metrics_dict_by_gw(skip_None=False)


@ns_metrics.route('/by_node')
class SensorsMetricsByNode(Resource):
    def get(self):
        '''get all metrics sorted by node_id / sensor_id'''

        return sensors.get_metrics_dict_by_node(skip_None=False)


@ns_metrics.route('/by_sensor')
class SensorsMetricsBySensor(Resource):
    def get(self):
        '''get all metrics sorted by sensor_id'''

        return sensors.get_metrics_dict_by_sensor(skip_None=False)


@ns_metrics.route('/default')
class StateDefault(Resource):
    def put(self):
        '''reset state of all sensors to default value
           (reset metric "value")'''

        return sensors.default_values()


@ns_metrics.route('/reset')
class StateReset(Resource):
    def put(self):
        '''reset state and metadata of all sensors
           (reset metrics "value", "hits_total",
           "hit_timestamp", "duration_seconds")'''

        return sensors.reset_values()


@ns_state.route('/reload')
class StateReload(Resource):
    def put(self):
        '''reload switchboard configuration'''

        return sensors.reload_config(pars)


@ns_state.route('/dump')
class StateDump(Resource):
    def get(self):
        '''get all data of all sensors'''

        return sensors.get_sensors_dump_dict()


@ns_info.route('/version')
class InfoVersion(Resource):
    def get(self):
        '''get app version and resources info'''

        return get_build_info()


@ns_info.route('/myip')
class InfoIP(Resource):
    def get(self):
        '''show my IP address + other client info'''

        ret = {
            'ip': request.remote_addr,
            'user-agent': request.user_agent.string,
            'platform': request.user_agent.platform,
            'browser': request.user_agent.browser,
            'version': request.user_agent.version
        }

        return ret


# Web interface


@app.route('/')
@app.route('/sensors')
def table():
    return render_template('sensors.html',
                           time_locale=pars.time_locale,
                           async_mode=sio.async_mode,
                           data=sensors.get_sensors_dump_dict())


@app.route('/log')
def log():
    return render_template('log.html',
                           time_locale=pars.time_locale,
                           async_mode=sio.async_mode,
                           data=sensors.get_sensors_dump_dict())


@app.route('/doc')
def doc():
    return render_template('doc.html', async_mode=sio.async_mode)


@app.route('/prom')
def prom():
    return render_template('prom.html', async_mode=sio.async_mode)


# Prometheus metrics
@app.route('/metrics')
def metrics():
    return Response(generate_latest(REGISTRY), mimetype=CONTENT_TYPE_LATEST)


# start scheduler
scheduler = BackgroundScheduler()
scheduler.start()
scheduler.add_job(func=sensors.update_sensors_ttl,
                  trigger=IntervalTrigger(seconds=1),
                  id='ttl_job',
                  name='update ttl counters every second',
                  replace_existing=True)


# start http server
def run_server():
    logger.info("http server listen {}:{}".format(pars.addr, pars.port))
    log = LoggingLogAdapter(logger, level=logging.DEBUG)
    errlog = LoggingLogAdapter(logger, level=logging.ERROR)
    http_server = WSGIServer((pars.addr, pars.port),
                             app,
                             log=log,
                             error_log=errlog)
    sensors.load_config(pars)
    http_server.serve_forever()
