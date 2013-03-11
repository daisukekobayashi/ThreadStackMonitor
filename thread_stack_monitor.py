#! /usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import argparse

import numpy
import matplotlib
matplotlib.use('GTKAgg')
import matplotlib.pyplot as plt
import matplotlib.animation as animation

#import sys
#sys.path.append('gen-py')

from tsm import TSMonitor
import tsm.ttypes as tsm

from thrift import Thrift
from thrift.transport import TSocket
from thrift.transport import TTransport
from thrift.protocol import TBinaryProtocol
from thrift.server import TServer

from winappdbg import System, Process, Thread

parser = argparse.ArgumentParser()

subparsers = parser.add_subparsers(dest="subcommand", help="sub-command help")

parser_server = subparsers.add_parser("server")
parser_server.add_argument("--port", action="store", dest="port", default=9090,type=int)

parser_monitor = subparsers.add_parser("monitor")
parser_monitor.add_argument("--pid", action="store", dest="pid", type=int)
parser_monitor.add_argument("--host", action="store", dest="host", type=str,
        default="127.0.0.1")
parser_monitor.add_argument("--port", action="store", dest="port", type=int,
        default=9090)
parser_monitor.add_argument("--interval", action="store", dest="interval",
        type=int, default=1000)
parser_monitor.add_argument("--stacksize", action="store", dest="stacksize",
        type=int, default=1024)
parser_monitor.add_argument("--maxplot", action="store", dest="maxplot",
        type=int, default=20)

arg = parser.parse_args()


def get_pid(system, process_name):
    for (process, name) in system.find_processes_by_filename(process_name):
        return process.get_pid()


def get_thread_stack(thread):
    try:
        stack_limit, stack_base = thread.get_stack_range()
        return stack_base - stack_limit
    except WindowsError:
        return -1


class TSMonitorHandler:
    def __init__(self):
        self._system = System()
        self._system.request_debug_privileges()
        self._process = {}
        for process in self._system:
            self._process[process.get_pid()] = process

    def ping(self):
        print "function ping called."
        return 0

    def refresh(self):
        print "function refresh called."
        self.__init__()
        return 0

    def process(self, id):

        p = self._process[id]

        process = tsm.Process()
        process.id = id
        if id == 0:
            process.name = "System Idle Process"
        elif id == 4:
            process.name = "System"
        else:
            process.name = os.path.basename(p.get_filename())

        p.scan_threads()

        tids = p.get_thread_ids()
        #tids.sort()
        process.num_threads = len(tids)
        
        process.thread = []
        for tid in tids:
            # Suspend the thread executior
            try:
                th = p.get_thread(tid)
                th.suspend()
                stack_limit, stack_base = th.get_stack_range()
                thread = tsm.Thread()
                thread.id = tid
                thread.stack_size = stack_base - stack_limit
                process.thread.append(thread)

            except WindowsError:
                thread = tsm.Thread()
                thread.id = tid
                thread.stack_size = -1
                process.thread.append(thread)

            # Resume the thread execution
            finally:
                th.resume()

        return process

def gen_log_str(tid, val):
    s = ""
    for i in range(len(tid)):
        if tid[i] != "":
            s = s + ", " + tid[i] + ":" + str(val[i])

    return s


class ThreadStackGraph:
    def __init__(self, pid, host, port):
        logging.basicConfig(filename = "thread_stack.log",
                            level = logging.INFO,
                            format = "%(asctime)s %(message)s")
        self._host = host
        self._port = port
        self._transport = TSocket.TSocket(self._host, self._port)
        self._transport = TTransport.TBufferedTransport(self._transport)
        self._protocol = TBinaryProtocol.TBinaryProtocol(self._transport)
        self._client = TSMonitor.Client(self._protocol)
        self._transport.open()
        self._client.refresh()

        self._pid = pid 
        self._maxplot = arg.maxplot
        self._pos = list(numpy.arange(self._maxplot) + 0.5)
        self._pos.reverse()

    def update_rects(self, num, ax, rects):
        process = self._client.process(self._pid)
        #pos = np.arange(process.num_threads) + 0.5
        val = [0] * self._maxplot
        tid = [""] * self._maxplot
        for i in range(len(process.thread)):
            tid[i] = str(process.thread[i].id)
            val[i] = process.thread[i].stack_size / 1024

        for i, rect in enumerate(rects):
            rect.set_width(val[i])

        #self.autolabel(rects)
        plt.yticks(self._pos, tid)
        #logging.info(str(val)[1:-1])
        logging.info(gen_log_str(tid, val))

    def autolabel(self, rects):
        for rect in rects:
            width = int(rect.get_width())
            plt.text(1.1 * width, rect.get_y() + rect.get_height() / 2.,
                     "%d" % width, ha="left", va="center")


    def show(self):
        
        self._client.refresh()
        process = self._client.process(self._pid)
        
        val = [0] * self._maxplot
        tid = [0] * self._maxplot
        for i in range(len(process.thread)):
            tid[i] = process.thread[i].id
            val[i] = process.thread[i].stack_size / 1024
            #tids.append(th.id)
            #val.append(int(th.stack_size / 1024))

        logging.info("----------thread stack logging started----------")
        logging.info(str(tid)[1:-1])

        fig = plt.figure(figsize=(6, 12))
        ax = fig.add_subplot(111)
        ax.set_title("Thread Stack Usage")
        plt.yticks(self._pos, tid)
        #plt.yticks(self._pos, [str(th.id) for th in process.thread])
        ax.set_xlabel("Thread Stack Size [Kbytes]")
        ax.set_xlim([0, arg.stacksize])
        ax.grid(True)
        rects = plt.barh(self._pos, val, align="center")
        ani = animation.FuncAnimation(fig, self.update_rects, fargs=(ax, rects),
                                      interval=arg.interval, blit=False)
        plt.show()
        
        self._transport.close()
        logging.info("----------thread stack logging end----------")


        
def server_main():
    try:
        arg = parser.parse_args()
        
        handler = TSMonitorHandler()
        processor = TSMonitor.Processor(handler)
        transport = TSocket.TServerSocket(port=arg.port)
        tfactory = TTransport.TBufferedTransportFactory()
        pfactory = TBinaryProtocol.TBinaryProtocolFactory()

        server = TServer.TThreadPoolServer(processor, transport, tfactory, pfactory)

        print 'Starting the server...'
        server.serve()
        print 'done.'
    except:
        sys.exit()


def monitor_main():
    tsgraph = ThreadStackGraph(arg.pid, arg.host, arg.port)
    tsgraph.show()


if __name__ == '__main__':

    if arg.subcommand  == "server":
        print "running server"
        server_main()
    elif arg.subcommand == "monitor":
        print "runnning monitor"
        monitor_main()
