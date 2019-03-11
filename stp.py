import socket
import random
import queue
import threading
import time
import logging


SEG_SYN = 0x00000001
SEG_ACK = 0x00000002
SEG_DATA = 0x00000004
SEG_FIN = 0x00000008

STAT_CLOSED = 0
STAT_LISTEN = 1
STAT_SYN_SENT = 2
STAT_SYN_RCVD = 3
STAT_ESTABLISHED = 4
STAT_CLOSE_WAIT = 5
STAT_LAST_ACK = 6
STAT_FIN_WAIT_1 = 7
STAT_FIN_WAIT_2 = 8
STAT_CLOSING = 9
STAT_TIME_WAIT = 10

UNRCVD_TAG = -1

start_time = time.time()


class STPSocket:
    def __init__(self, mws, mss, gamma):
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.peer_addr = ("host", "port")
        self.mws = mws
        self.mss = mss
        self.gamma = gamma

        self.timeout_ms = 500 + gamma * 250
        self.timers = {}

        self.seq_num = 0
        self.peer_ack_num = 0
        self.ack_num = 0
        self.peer_seq_num = 0

        # self.window = mws

        self.last_peer_ack_num = 0

        self.peer_seq_num = 0

        self.PLD = None

        self.status = STAT_CLOSED
        self.recv_queue = queue.Queue()
        self.recv_thread = threading.Thread(target=self.__recv_thread_func)

        self.recv_buf = []
        self.sent_segs = {}

        self.logger = logging.getLogger("stp")
        self.logger.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter(fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        self.output_info = queue.Queue()

        self.lock_counter_timeout = threading.Lock()
        self.counter_timeout = 0
        self.counter_fast_retransmission = 0
        self.counter_dup_ack_sent = 0
        self.counter_dup_ack_recv = 0

        self.counter_recv = 0
        self.counter_data_recv = 0
        self.counter_corr_recv = 0
        self.counter_dup_data_recv = 0

    def __timer_callback(self, seq):
        self.logger.warning("seq %d ACK timeout" % (seq))

        seg = self.sent_segs[seq]
        self.PLD.send(seg, self.peer_addr, self.output_info)

        self.lock_counter_timeout.acquire()
        self.counter_timeout += 1
        self.lock_counter_timeout.release()

        # self.udp_socket.sendto(seg.to_byte(), self.peer_addr)

        self.timers[seq] = Timer(self.timeout_ms, self.__timer_callback, seq)
        self.timers[seq].start()
        self.logger.warning("Sending Time out, set retransmit")

    def __recv_thread_func(self):
        self.logger.info("Recv thread start")
        while self.status != STAT_CLOSED:
            data, peer_addr = self.udp_socket.recvfrom(self.mws + 4 * 5)
            if self.peer_addr == ("host", "port"):
                self.peer_addr = peer_addr

            seg = Segment()
            seg.from_byte(data)
            self.counter_recv += 1

            self.peer_seq_num = seg.sequence_num
            if self.peer_ack_num <= seg.ack_num:
                self.peer_ack_num = seg.ack_num

            if seg.flag & SEG_ACK:
                self.is_reack = self.peer_ack_num == seg.ack_num
                if self.is_reack:
                    self.logger.warning("Got same ACK, seg ack: " + str(seg.ack_num))

            if self.status == STAT_LISTEN:
                self.__listen_handler(seg)
            elif self.status == STAT_SYN_RCVD:
                self.__syn_rcvd_handler(seg)
            elif self.status == STAT_SYN_SENT:
                self.__syn_sent_handler(seg)
            elif self.status == STAT_ESTABLISHED:
                self.__established_handler(seg)
            elif self.status == STAT_FIN_WAIT_1:
                self.__fin_wait_1_handler(seg)
            elif self.status == STAT_FIN_WAIT_2:
                self.__fin_wait_2_handler(seg)
            elif self.status == STAT_CLOSE_WAIT:
                self.__close_wait_handler(seg)
            elif self.status == STAT_LAST_ACK:
                self.__last_ack_handler(seg)
            else:
                self.status = STAT_CLOSED

        self.logger.info("Recv thread exit")

    def __syn_sent_handler(self, recv_seg):
        if self.status != STAT_SYN_SENT:
            return False
        self.logger.info("STP change to SYN_SENT")

        if recv_seg.flag == SEG_SYN | SEG_ACK: # and recv_seg.ack_num == self.seq_num:
            self.output_info.put("rcv\t%f\tSA\t%d\t%d\t%d" % (time.time() - start_time, recv_seg.sequence_num, len(recv_seg.payload), recv_seg.ack_num))

            self.last_peer_ack_num = recv_seg.ack_num

            self.ack_num = self.peer_seq_num + 1
            ack_seg = Segment(self.seq_num, self.ack_num, SEG_ACK)
            self.udp_socket.sendto(ack_seg.to_byte(), self.peer_addr)
            self.logger.info("SYN_SENT sent ACK seg")
            self.output_info.put("snd\t%f\tA\t%d\t%d\t%d" % (time.time() - start_time, ack_seg.sequence_num, len(ack_seg.payload), ack_seg.ack_num))
            self.status = STAT_ESTABLISHED
        return True

    def __listen_handler(self, recv_seg):
        if self.status != STAT_LISTEN:
            return False
        self.logger.info("STP change to LISTEN")

        if recv_seg.flag == SEG_SYN:
            self.output_info.put("rcv\t%f\tS\t%d\t%d\t%d" % (time.time() - start_time, recv_seg.sequence_num, len(recv_seg.payload), recv_seg.ack_num))
            self.ack_num = self.peer_seq_num + 1
            acksyn_seg = Segment(self.seq_num, self.ack_num, SEG_SYN | SEG_ACK)
            self.udp_socket.sendto(acksyn_seg.to_byte(), self.peer_addr)

            self.logger.info("LISTEN sent ACK|SYN seg")
            self.output_info.put("snd\t%f\tSA\t%d\t%d\t%d" % (time.time() - start_time, acksyn_seg.sequence_num, len(acksyn_seg.payload), acksyn_seg.ack_num))
            self.status = STAT_SYN_RCVD
            self.seq_num += 1
        return True

    def __syn_rcvd_handler(self, recv_seg):
        if self.status != STAT_SYN_RCVD:
            return False
        self.logger.info("STP change to SYN_RCVD")

        if recv_seg.flag == SEG_ACK and recv_seg.ack_num == self.seq_num:
            self.output_info.put("rcv\t%f\tA\t%d\t%d\t%d" % (time.time() - start_time, recv_seg.sequence_num, len(recv_seg.payload), recv_seg.ack_num))
            self.status = STAT_ESTABLISHED

        return True

    def __established_handler(self, recv_seg):
        if self.status != STAT_ESTABLISHED:
            return False
        self.logger.debug("STP ESTABLISHED")

        if recv_seg.flag == SEG_DATA:
            self.counter_data_recv += 1

            # 错误到达
            if not recv_seg.is_completed:
                self.output_info.put("rcv/corr\t%f\tD\t%d\t%d\t%d" % (time.time() - start_time, recv_seg.sequence_num, len(recv_seg.payload), recv_seg.ack_num))
                self.udp_socket.sendto(Segment(self.seq_num, self.ack_num, SEG_ACK).to_byte(),
                                       self.peer_addr)
                self.logger.warning("Got corr data seg")
                self.counter_corr_recv += 1
            else:
                self.output_info.put("rcv\t%f\tD\t%d\t%d\t%d" % (time.time() - start_time, recv_seg.sequence_num, len(recv_seg.payload), recv_seg.ack_num))
                if len(self.recv_buf) < recv_seg.sequence_num - 1 + len(recv_seg.payload):
                    for i in range(recv_seg.sequence_num - 1 + len(recv_seg.payload) - len(self.recv_buf)):
                        self.recv_buf.append(UNRCVD_TAG)

                for i in range(len(recv_seg.payload)):
                    if self.recv_buf[i + recv_seg.sequence_num - 1] == UNRCVD_TAG:
                        self.recv_buf[i + recv_seg.sequence_num - 1] = recv_seg.payload[i]
                    else:
                        self.logger.warning("dup data. seq: " + str(recv_seg.sequence_num))
                        self.counter_dup_data_recv += 1
                        break

#           # 非重复到达或乱序到达
            last_ack = self.ack_num
            for i in range(len(self.recv_buf)):
                if i == len(self.recv_buf) - 1 or self.recv_buf[i + 1] == UNRCVD_TAG:
                    if i != 0:
                        self.ack_num = i + 1 + 1
                    else:
                        self.ack_num = 1
                    break

            if last_ack == self.ack_num:
                self.output_info.put("snd/DA\t%f\tA\t%d\t%d\t%d" % (time.time() - start_time, self.seq_num, 0, self.ack_num))
                self.counter_dup_ack_sent += 1
            else:
                self.output_info.put("snd/A\t%f\tA\t%d\t%d\t%d" % (time.time() - start_time, self.seq_num, 0, self.ack_num))

            self.logger.info("sending ACK. stp ack_num: %d, seg seg_num: %d" % (self.ack_num, recv_seg.sequence_num))

            self.udp_socket.sendto(Segment(self.seq_num, self.ack_num, SEG_ACK).to_byte(),
                                   self.peer_addr)

        elif recv_seg.flag == SEG_ACK:
            # 根据recv.seg.ack_num更新窗口
            # 如果这是重复的ACK，且窗口小于于分段大小
            #   重传

            if self.is_reack:
                self.output_info.put("rcv/DA\t%f\tA\t%d\t%d\t%d" % (time.time() - start_time, recv_seg.sequence_num, len(recv_seg.payload), recv_seg.ack_num))
                self.counter_dup_ack_recv += 1
            else:
                self.output_info.put("rcv\t%f\tA\t%d\t%d\t%d" % (time.time() - start_time, recv_seg.sequence_num, len(recv_seg.payload), recv_seg.ack_num))

            self.logger.info("got ACK. seg ack_num: %d, stp seg_num: %d" % (recv_seg.ack_num, self.seq_num))

            if recv_seg.ack_num < self.last_peer_ack_num:
                self.logger.warning('a ACK had acked. Would not retransmite')
                return True

            window = self.mws - (self.seq_num - recv_seg.ack_num)
            for key in self.timers.keys():
                if key <= recv_seg.ack_num:
                    self.timers[key].pause()

            if self.is_reack and window < self.mss:
                last_acked_seg = self.sent_segs[self.peer_ack_num]
                seg = self.sent_segs[self.peer_ack_num + len(last_acked_seg.payload)]
                self.logger.warning("Fast retransmit seg: " + str(seg.sequence_num))
                self.PLD.send(seg, self.peer_addr, self.output_info)
                self.counter_fast_retransmission += 1

        elif recv_seg.flag == SEG_FIN:
            self.output_info.put("rcv\t%f\tF\t%d\t%d\t%d" % (time.time() - start_time, recv_seg.sequence_num, len(recv_seg.payload), recv_seg.ack_num))
            self.logger.info("Recv a FIN")
            self.ack_num = self.peer_seq_num + 1
            ack_seg = Segment(self.seq_num, self.ack_num, SEG_ACK)
            self.udp_socket.sendto(ack_seg.to_byte(), self.peer_addr)
            self.output_info.put("snd\t%f\tA\t%d\t%d\t%d" % (time.time() - start_time, ack_seg.sequence_num, len(ack_seg.payload), ack_seg.ack_num))
            self.status = STAT_CLOSE_WAIT
            self.__close_wait_handler(None)

        return True

    def __fin_wait_1_handler(self, recv_seg):
        if self.status != STAT_FIN_WAIT_1:
            return False

        self.logger.info("STP change to FIN_WAIT_1")
        if recv_seg.flag == SEG_ACK and recv_seg.ack_num == self.seq_num:
            self.output_info.put("rcv\t%f\tA\t%d\t%d\t%d" % (time.time() - start_time, recv_seg.sequence_num, len(recv_seg.payload), recv_seg.ack_num))
            self.status = STAT_FIN_WAIT_2

        return True

    def __fin_wait_2_handler(self, recv_seg):
        if self.status != STAT_FIN_WAIT_2:
            return False
        self.logger.info("STP change to FIN_WAIT_2")

        if recv_seg.flag == SEG_FIN:
            self.output_info.put("rcv\t%f\tF\t%d\t%d\t%d" % (time.time() - start_time, recv_seg.sequence_num, len(recv_seg.payload), recv_seg.ack_num))
            self.ack_num = self.peer_seq_num + 1
            ack_seg = Segment(self.seq_num, self.ack_num, SEG_ACK)
            self.udp_socket.sendto(ack_seg.to_byte(), self.peer_addr)
            self.output_info.put("snd\t%f\tA\t%d\t%d\t%d" % (time.time() - start_time, ack_seg.sequence_num, len(ack_seg.payload), ack_seg.ack_num))
            self.status = STAT_CLOSED

        return True

    def __close_wait_handler(self, recv_seg):
        if self.status != STAT_CLOSE_WAIT:
            return False
        self.logger.info("STP change to CLOSE_WAIT")

        fin_seg = Segment(self.seq_num, self.ack_num, SEG_FIN)
        self.udp_socket.sendto(fin_seg.to_byte(), self.peer_addr)
        self.output_info.put("snd\t%f\tF\t%d\t%d\t%d" % (time.time() - start_time, fin_seg.sequence_num, len(fin_seg.payload), fin_seg.ack_num))
        self.seq_num += 1
        self.status = STAT_LAST_ACK

        return True

    def __last_ack_handler(self, recv_seg):
        if self.status != STAT_LAST_ACK:
            return False
        self.logger.info("STP change to LAST_ACK")

        if recv_seg.flag == SEG_ACK and recv_seg.ack_num == self.seq_num:
            self.output_info.put("rcv\t%f\tA\t%d\t%d\t%d" % (time.time() - start_time, recv_seg.sequence_num, len(recv_seg.payload), recv_seg.ack_num))
            self.status = STAT_CLOSED

        return True

    def get_output_info(self):
        return self.output_info

    def connect(self, host, port):
        # Send SYN and change status to SYN_SENT
        self.status = STAT_SYN_SENT
        self.recv_thread.start()

        self.seq_num = 0
        self.ack_num = 0
        # self.window = self.mws

        self.peer_addr = (host, port)

        syn_seg = Segment(self.seq_num, self.ack_num, SEG_SYN)
        self.udp_socket.sendto(syn_seg.to_byte(), self.peer_addr)
        self.output_info.put("snd\t%f\tS\t%d\t%d\t%d" % (time.time() - start_time, syn_seg.sequence_num, len(syn_seg.payload), syn_seg.ack_num))
        self.logger.info("Connect. Sent SYN seg")
        self.seq_num += 1

        while self.status != STAT_ESTABLISHED:
            pass    # TODO should sleep

    def bind(self, host, port):
        self.udp_socket.bind((host, port))

    def listen(self):
        self.seq_num = 0
        self.ack_num = 0
        # self.window = self.mws

        self.status = STAT_LISTEN

    def accept(self):
        if self.status != STAT_LISTEN:
            return False

        self.recv_thread.start()

        while self.status != STAT_ESTABLISHED:
            pass    # TODO should sleep

    def close(self):
        if self.status != STAT_ESTABLISHED:
            return

        fin_seg = Segment(self.seq_num, self.ack_num, SEG_FIN)
        self.udp_socket.sendto(fin_seg.to_byte(), self.peer_addr)
        self.output_info.put("snd\t%f\tF\t%d\t%d\t%d" % (time.time() - start_time, fin_seg.sequence_num, len(fin_seg.payload), fin_seg.ack_num))
        self.logger.info("Close. Sent FIN seg")
        self.seq_num += 1

        self.status = STAT_FIN_WAIT_1

        for timer in self.timers.values():
            timer.pause()

        while self.status != STAT_CLOSED:
            pass

    def set_pld(self, p_drop, p_duplicate, p_corrupt, p_order, max_order, p_delay, max_delay, seed):
        global start_time
        start_time = time.time()
        self.PLD = PLD(p_drop, p_duplicate, p_corrupt, p_order, max_order, p_delay, max_delay, seed, self.udp_socket)

    def recv(self, buf_size):
        while len(self.recv_buf) == 0:
            pass

        result = bytes(self.recv_buf)

        self.recv_buf.clear()

        return result

    def send(self, buf):
        i = 0

        while i < len(buf):
            seg_len = min(self.mss, len(buf) - i)
            # 当窗口大于segment大小时
            window = self.mws - (self.seq_num - self.peer_ack_num)
            if window >= seg_len:
                # 发送
                window = self.mws - (self.seq_num - self.peer_ack_num) - seg_len

                self.logger.info("send seg. seq: %d, window: %d" % (self.seq_num, window))

                seg = Segment(self.seq_num, self.ack_num, SEG_DATA, window, buf[i: i + seg_len])

                self.timers[self.seq_num + seg_len] = Timer(self.timeout_ms, self.__timer_callback, self.seq_num + seg_len)
                self.timers[self.seq_num + seg_len].start()
                self.sent_segs[self.seq_num + seg_len] = seg

                self.PLD.send(seg, self.peer_addr, self.output_info)
                # self.udp_socket.sendto(seg.to_byte(), self.peer_addr)

                if self.seq_num == 1:
                    self.sent_segs[1] = seg

                self.seq_num += seg_len

                i += seg_len
                continue

            # 等待窗口恢复
            window = self.mws - (self.seq_num - self.peer_ack_num)
            while window < seg_len:
                window = self.mws - (self.seq_num - self.peer_ack_num)
                pass

        while self.peer_ack_num != self.seq_num:
            pass


class Segment:
    def __init__(self, sequence_num=0, ack_num=0, flag=0, window=0, payload=b''):
        self.sequence_num = sequence_num
        self.ack_num = ack_num
        self.flag = flag
        self.window = window
        self.checksum = 0
        self.payload = payload

        self.is_completed = False

    def set_payload(self, payload):
        self.payload = b''
        self.payload += payload

    def calc_checksum(self):
        self.checksum = self.sequence_num + self.ack_num + self.flag + self.window
        for i in range(0, len(self.payload), 4):
            if i + 4 < len(self.payload):
                tmp = self.payload[i: i + 4]
            else:
                tmp = self.payload[i:]
                for j in range(4 - (len(self.payload) - i)):
                    tmp += b'\x00'

            self.checksum += int.from_bytes(tmp, byteorder='big', signed=False) & 0xffffffff
        self.checksum &= 0xffffffff

    def to_byte(self):
        self.calc_checksum()

        data = self.sequence_num.to_bytes(4, 'big', signed=False)
        data += self.ack_num.to_bytes(4, 'big', signed=False)
        data += self.flag.to_bytes(4, 'big', signed=False)
        data += self.window.to_bytes(4, 'big', signed=False)
        data += self.checksum.to_bytes(4, 'big', signed=False)
        data += self.payload
        return data

    def from_byte(self, data):
        self.sequence_num = int.from_bytes(data[0:4], byteorder='big', signed=False)
        self.ack_num = int.from_bytes(data[4:8], byteorder='big', signed=False)
        self.flag = int.from_bytes(data[8:12], byteorder='big', signed=False)
        self.window = int.from_bytes(data[12:16], byteorder='big', signed=False)
        self.payload = data[20:]

        checksum = int.from_bytes(data[16:20], byteorder='big', signed=False)
        self.calc_checksum()

        self.is_completed = checksum == self.checksum
        return checksum == self.checksum


class PLD:
    def __init__(self, p_drop, p_duplicate, p_corrupt, p_order, max_order, p_delay, max_delay, seed,
                 udp_sock):
        self.p_drop = p_drop
        self.p_duplicate = p_duplicate
        self.p_corrupt = p_corrupt
        self.p_order = p_order
        self.max_order = max_order
        self.p_delay = p_delay
        self.max_delay = max_delay

        self.udp_sock = udp_sock

        random.seed(seed)

        self.logger = logging.getLogger("PLD")
        self.logger.setLevel(logging.INFO)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter(fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        self.send_queue = queue.Queue()
        self.order_data = None
        self.order_counter = max_order

        self.counter_handled = 0
        self.counter_dropped = 0
        self.counter_corrupted = 0
        self.counter_re_ordered = 0
        self.counter_duplicated = 0
        self.counter_delayed = 0

    def __delay_seg(self, seg_addr, ms):
        timer = Timer(ms, self.__delay_callback, seg_addr)
        timer.start()

    def __delay_callback(self, argv):
        self.__send(argv[0], argv[1], True)

    def __send(self, buf, addr, no_flush=False):
        self.send_queue.put((buf, addr))
        self.counter_handled += 1

        if self.order_data is not None:
            self.order_counter -= 1

            if self.order_counter == 0:
                self.send_queue.put(self.order_data)
                self.order_data = None

        if not no_flush:
            self.flush()

    def resend(self, seg, addr, output_info):
        buf = seg.to_byte()
        self.__send(buf, addr)
        output_info.put("snd/RXT\t%f\tD\t%d\t%d\t%d" % (time.time() - start_time, seg.sequence_num, len(seg.payload), seg.ack_num))

    def send(self, seg, addr, output_info):

        buf = seg.to_byte()
        # drop
        p = random.random()
        if p < self.p_drop:
            self.logger.info("drop")
            self.counter_dropped += 1
            output_info.put("drop\t%f\tD\t%d\t%d\t%d" % (time.time() - start_time, seg.sequence_num, len(seg.payload), seg.ack_num))
            return

        # duplicate
        p = random.random()
        if p < self.p_duplicate:
            self.logger.info("duplicate")
            self.counter_duplicated += 1
            self.__send(buf, addr)
            self.__send(buf, addr)
            output_info.put("snd/dup\t%f\tD\t%d\t%d\t%d" % (time.time() - start_time, seg.sequence_num, len(seg.payload), seg.ack_num))
            return

        # corrupt
        p = random.random()
        if p < self.p_corrupt:
            self.logger.info("corrupt")
            self.counter_corrupted += 1
            tmparr = list(buf)
            tmparr[15] = (tmparr[15] & 0xfe) | (~tmparr[15] & 0x01)    # 翻转第15个字节的第一位
            self.__send(bytes(tmparr), addr)
            output_info.put("snd/corr\t%f\tD\t%d\t%d\t%d" % (time.time() - start_time, seg.sequence_num, len(seg.payload), seg.ack_num))
            return

        # order
        p = random.random()
        if p < self.p_order:
            self.logger.info("order")
            if self.order_data is None:
                self.order_data = (buf, addr)
                self.order_counter = self.max_order
                self.counter_re_ordered += 1
                output_info.put("snd/rord\t%f\tD\t%d\t%d\t%d" % (time.time() - start_time, seg.sequence_num, len(seg.payload), seg.ack_num))
            else:
                output_info.put("snd\t%f\tD\t%d\t%d\t%d" % (time.time() - start_time, seg.sequence_num, len(seg.payload), seg.ack_num))
                self.__send(buf, addr)
            return

        # delay
        p = random.random()
        if p < self.p_delay:
            self.counter_delayed += 1
            self.logger.info("delay")
            t = self.max_delay * random.random()
            self.__delay_seg((buf, addr), t)
            output_info.put("delay\t%f\tD\t%d\t%d\t%d" % (time.time() - start_time, seg.sequence_num, len(seg.payload), seg.ack_num))
            return

        output_info.put("snd\t%f\tD\t%d\t%d\t%d" % (time.time() - start_time, seg.sequence_num, len(seg.payload), seg.ack_num))
        self.__send(buf, addr)
        return

    def flush(self):
        while not self.send_queue.empty():
            buf, addr = self.send_queue.get()
            self.udp_sock.sendto(buf, addr)


class Timer:
    def __init__(self, ms, callback, argv):
        self.__user_setting = ms
        self.__times = self.__user_setting / 10
        self.__callback = callback
        self.__argv = argv

        self.__status = 0
        self.__timer_thread = threading.Thread(target=self.__timer_func)

    def __timer_func(self):
        while self.__times > 0:
            time.sleep(0.01)
            if self.__status == 0:
                return
            else:
                self.__times -= 1

        self.__callback(self.__argv)

    def start(self):
        self.__status = 1

        self.__timer_thread = threading.Thread(target=self.__timer_func)
        self.__timer_thread.start()

    def pause(self):
        self.__status = 0

    def reset(self, ms=-1):
        if ms > 0:
            self.__user_setting = ms

        self.__times = self.__user_setting / 50


class Test:
    def __init__(self):
        self.timer = Timer(2000, self.timer_test, self)

    def timer_test(self, argv):
        print("alarm. time: %s, info: %s" % (str(time.time()), type(argv)))

    def test(self):
        print("Start time: " + str(time.time()))
        self.timer.start()

        time.sleep(1)

        print("Pause time: " + str(time.time()))
        self.timer.pause()

        time.sleep(2)

        print("restart time: " + str(time.time()))
        self.timer.start()


def main():
    test = Test()
    test.test()


if __name__ == '__main__':
    main()
