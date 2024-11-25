package org.electroncash.electroncash3

import android.os.Bundle
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.Spinner
import androidx.fragment.app.Fragment
import androidx.fragment.app.replace
import androidx.fragment.app.commit


class TransactionsFragment : Fragment(R.layout.transactions), MainFragment {
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val spinner: Spinner = view.findViewById(R.id.spnTxType)
        ArrayAdapter.createFromResource(
            activity!!,
            R.array.transaction_type,
            android.R.layout.simple_spinner_item
        ).also { adapter ->
            adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
            spinner.adapter = adapter
        }

        spinner.onItemSelectedListener = object :
            AdapterView.OnItemSelectedListener {
            override fun onItemSelected(parent: AdapterView<*>, view: View?,
                                        position: Int, id: Long) {
                when (position) {
                    0 -> replaceTxFragment<BchTransactionsFragment>()
                    1 -> replaceTxFragment<TokenTransactionsFragment>()
                    2 -> replaceTxFragment<FusionFragment>()
                }
            }
            override fun onNothingSelected(parent: AdapterView<*>) {}
        }
    }

    private inline fun <reified T : Fragment> replaceTxFragment() {
        requireActivity().supportFragmentManager.commit {
            setReorderingAllowed(true)
            replace<T>(R.id.transactions_container)
        }
    }
}
