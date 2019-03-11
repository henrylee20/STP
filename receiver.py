import stp
import time
import sys


def main(argv):
    port = int(argv[1])
    filename = argv[2]

    sock = stp.STPSocket(1000, 100, 2)
    sock.bind('127.0.0.1', port)

    sock.listen()
    sock.accept()

    while sock.status != stp.STAT_CLOSED:
        pass
    data = sock.recv(1000)

    fp = open(filename, 'wb')
    fp.write(data)
    fp.close()

    output_info = sock.output_info
    output_text = []
    while not output_info.empty():
        output_text.append(output_info.get() + '\n')
    output_text.append('========================================' + '\n')
    output_text.append('Amount of data received (bytes)\t' + str(len(data)) + '\n')
    output_text.append('Total Segments Received\t' + str(sock.counter_recv) + '\n')
    output_text.append('Data Segments Received\t' + str(sock.counter_data_recv) + '\n')
    output_text.append('Data Segments with Bit Errors\t' + str(sock.counter_corr_recv) + '\n')
    output_text.append('Duplicate data segments received\t' + str(sock.counter_dup_data_recv) + '\n')
    output_text.append('Duplicate ACKs sent\t' + str(sock.counter_dup_ack_sent) + '\n')
    output_text.append('========================================' + '\n')

    fp = open('Receiver_log.txt', 'w')
    fp.writelines(output_text)
    fp.close()


if __name__ == '__main__':
    main(sys.argv)
    exit(0)


sock = stp.STPSocket(100, 10, 2)

sock.bind('127.0.0.1', 2345)
sock.listen()
sock.accept()

time.sleep(5)
data = sock.recv(1000)
print(data)
time.sleep(1)
output = sock.get_output_info()
while not output.empty():
    print(output.get())

print("total: " + str(sock.counter_recv))
print("data: " + str(sock.counter_data_recv))
print("corr data: " + str(sock.counter_corr_recv))
print("dup data: " + str(sock.counter_dup_data_recv))
print("dup ACK sent: " + str(sock.counter_dup_ack_sent))
