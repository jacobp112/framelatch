`timescale 1ns/1ps
`default_nettype none

module framelatch_tb;
    reg clk = 0;
    reg rst = 1;
    reg [7:0] in_data = 0;
    reg in_valid = 0;
    wire in_ready;
    reg in_abort = 0;
    wire [127:0] out_payload;
    wire [4:0] out_length;
    wire out_valid;
    reg out_ready = 0;
    wire [31:0] valid_frames, crc_errors, invalid_lengths;
    wire [31:0] incomplete_frames, discarded_bytes;
    reg [7:0] scenario = 0;

    framelatch uut (.*);

    // Assertions sample the results of the preceding rising edge.
    reg seen_edge = 0, previous_reset = 1, previous_stall = 0;
    reg [127:0] previous_payload;
    reg [4:0] previous_length;
    always @(posedge clk) begin
        if (seen_edge && previous_reset) begin
            assert (!out_valid && out_payload == 0 && out_length == 0)
                else $fatal(1, "reset failed to clear output");
            assert ({valid_frames, crc_errors, invalid_lengths,
                     incomplete_frames, discarded_bytes} == 160'b0)
                else $fatal(1, "reset failed to clear counters");
            assert (uut.state == 0 && uut.assembly == 0)
                else $fatal(1, "reset failed to clear parser");
        end
        if (seen_edge && previous_stall && !previous_reset) begin
            assert (out_valid && out_payload == previous_payload &&
                    out_length == previous_length)
                else $fatal(1, "output changed under backpressure");
        end
        seen_edge <= 1;
        previous_reset <= rst;
        previous_stall <= out_valid && !out_ready;
        previous_payload <= out_payload;
        previous_length <= out_length;
    end

    reg [2047:0] dump_path;
    initial begin
        if ($value$plusargs("dumpfile=%s", dump_path)) begin
            $dumpfile(dump_path);
            $dumpvars(0, framelatch_tb);
        end
    end
endmodule

`default_nettype wire
