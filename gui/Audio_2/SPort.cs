using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.IO;
using System.IO.Ports;
using UartApplication;
using define;
using System.Threading;



namespace define { 
    static class constant
    {
        public const byte EffectsEnable_ADD = 0x00;
        public const byte ODdrive_ADD = 0x01;
        public const byte ODGain_ADD = 0x02;
        public const byte TremWave_ADD = 0x03;
        public const byte TremDepth_ADD = 0x04;
        public const byte EchoTime_ADD = 0x05;
        public const byte EchoRepeat_ADD = 0x06;
        public const byte EchoLevel_ADD = 0x07;

        public const byte DistMix_ADD = 0x08;
        public const byte DistType_ADD = 0x09;

        public const byte ChorusLevel_ADD = 10;
        public const byte ChorusDepth_ADD = 11;
        public const byte ChorusRate_ADD = 12;

        public const byte ReberbeMix_ADD = 13;
        public const byte ReberbeType_ADD = 14;

    }
}


namespace UartApplication {
    public class Uart
    {
        private SerialPort MySerialPort;

        public Uart(int BaudRate, string COM)
        {
           
            MySerialPort = new SerialPort(portName: COM, baudRate: BaudRate);

                try
                {
                    MySerialPort.Open();
                }

                catch (IOException ex)
                {
                    Console.WriteLine(ex);
                }
            
        }

        public void setPort(string COMport)
        {
            if(COMport != "")
            {
                MySerialPort.Close();
                MySerialPort.PortName = COMport;
            }           
            try
            {
                MySerialPort.Open();
            }

            catch (IOException ex)
            {
                Console.WriteLine(ex);
            }
        }
  
        public void SetEffect(byte Address, byte DataHigh,byte DataLow) 
        {
            byte[] data = {Address, DataHigh , DataLow };
            
            try
            {
                //MySerialPort.Write(data, 0, data.Length);
                MySerialPort.Write(data, 0, 1);
                Thread.Sleep(1);
                MySerialPort.Write(data, 1, 1);
                Thread.Sleep(1);
                MySerialPort.Write(data, 2, 1);
                Thread.Sleep(1);

            }

            catch (IOException ex)
            {
                Console.WriteLine(ex);
            }
            
        }

        public void SetCodec(byte Address, byte DataHigh, byte DataLow)
        {
            byte[] data = { Address, DataHigh, DataLow };

            try
            {
                //MySerialPort.Write(data, 0, data.Length);
                MySerialPort.Write(data, 0, 1);
                Thread.Sleep(1);
                MySerialPort.Write(data, 1, 1);
                Thread.Sleep(1);
                MySerialPort.Write(data, 2, 1);
                Thread.Sleep(1);
            }

            catch (IOException ex)
            {
                Console.WriteLine(ex.Message);
            }

        }

        public void closeUART()
        {
           
            MySerialPort.Close(); 
        
        }

        
    }
}


/*namespace SerialPortV1
{
    class Program
    {
        static void Main(string[] args)
        {
            //MySerialPort.DataReceived += new SerialDataReceivedEventHandler(mySerialPort_DataReceived); // uart as a signal_handler -- see function below
            Uart MySerialPort = new Uart(BaudRate: 9600, COM: "COM2");

            MySerialPort.SetEffect();
           
            Console.ReadKey();

        }

        //public static void mySerialPort_DataReceived(object sender, SerialDataReceivedEventArgs e)
        //{
        //    try
        //    {
        //        Console.Write(MySerialPort.ReadExisting());
        //    }
        //    catch(IOException ex)
        //    {
        //        Console.WriteLine(ex);
        //    }


        //}


    }
}*/
