# STP

在UDP上模拟的简化TCP协议,写着玩,用于熟悉理解TCP协议.

模拟了一条有损信道,可以通过这条信道传输数据,并记录发送时信道上发生了什么.

### Usage

Receiver:

```bash
python receiver.py <端口> <接收到的文件名>
```

Sender:

```bash
python sender.py <IP> <端口> <文件名> <mws> <mss> <timeout_gamma> <丢包概率> <重复发送概率> <比特位错误概率> <乱序概率> <最长乱序数> <延迟概率> <虽大延迟数量> <随机数种子>
```