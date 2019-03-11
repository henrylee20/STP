import stp
import time
import sys


def main(argv):
    host = argv[1]
    port = int(argv[2])
    filename = argv[3]
    mws = int(argv[4])
    mss = int(argv[5])
    gamma = int(argv[6])
    p_drop = float(argv[7])
    p_dup = float(argv[8])
    p_corr = float(argv[9])
    p_order = float(argv[10])
    max_order = int(argv[11])
    p_delay = float(argv[12])
    max_delay = int(argv[13])
    seed = int(argv[14])

    fp = open(filename, 'br')
    data = fp.read()
    fp.close()

    sock = stp.STPSocket(mws, mss, gamma)
    sock.set_pld(p_drop, p_dup, p_corr, p_order, max_order, p_delay, max_delay, seed)
    sock.connect(host, port)

    sock.send(data)
    sock.close()

    output_info = sock.output_info
    output_text = []
    while not output_info.empty():
        output_text.append(output_info.get() + '\n')
    output_text.append('========================================' + '\n')
    output_text.append('Size of the file (in Bytes)\t' + str(len(data)) + '\n')
    output_text.append('Segment transmitted (include drop & RXT)\t' + str(sock.PLD.counter_handled + 4) + '\n')
    output_text.append('Number of Segment handled by PLD\t' + str(sock.PLD.counter_handled) + '\n')
    output_text.append('Number of Segment dropped\t' + str(sock.PLD.counter_dropped) + '\n')
    output_text.append('Number of Segment Corrupted\t' + str(sock.PLD.counter_corrupted) + '\n')
    output_text.append('Number of Segment Re-ordered\t' + str(sock.PLD.counter_re_ordered) + '\n')
    output_text.append('Number of Segment Duplicated\t' + str(sock.PLD.counter_duplicated) + '\n')
    output_text.append('Number of Segment Delayed\t' + str(sock.PLD.counter_delayed) + '\n')
    output_text.append('Number of Segment Retransmissions due to TIMEOUT\t' + str(sock.counter_timeout) + '\n')
    output_text.append('Number of Segment FAST RETRANSMISSION\t' + str(sock.counter_fast_retransmission) + '\n')
    output_text.append('Number of DUP ACK received\t' + str(sock.counter_dup_ack_recv) + '\n')
    output_text.append('========================================' + '\n')

    fp = open('Sender_log.txt', 'w')
    fp.writelines(output_text)
    fp.close()


if __name__ == '__main__':
    main(sys.argv)
    exit(0)


sock = stp.STPSocket(4, 2, 8)
sock.set_pld(0.2, 0.0, 0.0, 0.0, 2, 0.4, 2, 50)
sock.connect("127.0.0.1", 2345)
sock.send(b'0123456789abcdef')
time.sleep(5)
sock.close()
time.sleep(1)
output = sock.get_output_info()
while not output.empty():
    print(output.get())

print("PLD handled: " + str(sock.PLD.counter_handled))
print("dropped: " + str(sock.PLD.counter_dropped))
print("corrupted: " + str(sock.PLD.counter_corrupted))
print("re-ordered: " + str(sock.PLD.counter_re_ordered))
print("dup: " + str(sock.PLD.counter_duplicated))
print("delay: " + str(sock.PLD.counter_delayed))
print("timeout counter: " + str(sock.counter_timeout))
print("fast retransmission: " + str(sock.counter_fast_retransmission))
print("dup ACK recv: " + str(sock.counter_dup_ack_recv))
